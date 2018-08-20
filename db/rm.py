import logging
import mysql
import mysql.connector
import datetime
import collections
import datetime
import time
from webhook import send_webhook
from walkerArgs import parseArgs
import requests
import shutil

log = logging.getLogger(__name__)

RaidLocation = collections.namedtuple('RaidLocation', ['latitude', 'longitude'])
args = parseArgs()


class RmWrapper:
    def __init__(self, host, port, user, password, database, timezone, uniqueHash="123"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.timezone = timezone
        self.uniqueHash = uniqueHash

    def dbTimeStringToUnixTimestamp(self, timestring):
        dt = datetime.datetime.strptime(timestring, '%Y-%m-%d %H:%M:%S')
        unixtime = (dt - datetime.datetime(1970, 1, 1)).total_seconds()
        return unixtime

    def getNextRaidHatches(self, delayAfterHatch):
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return []
        cursor = connection.cursor()
        # query = (' SELECT start, latitude, longitude FROM raid LEFT JOIN gym ' +
        #    'ON raid.gym_id = gym.gym_id WHERE raid.start >= \'%s\''
        #    % str(datetime.datetime.now() - datetime.timedelta(hours = self.timezone)))
        dbTimeToCheck = datetime.datetime.now() - datetime.timedelta(hours=self.timezone)
        query = (' SELECT start, latitude, longitude FROM raid LEFT JOIN gym ' +
                 'ON raid.gym_id = gym.gym_id WHERE raid.end > \'%s\' ' % str(dbTimeToCheck) +
                 'AND raid.pokemon_id IS NULL')
        # print(query)
        # data = (datetime.datetime.now())
        cursor.execute(query)

        data = []
        log.debug("Result of raidQ query: %s" % str(query))
        for (start, latitude, longitude) in cursor:
            if latitude is None or longitude is None:
                log.warning("lat or lng is none")
                continue
            timestamp = self.dbTimeStringToUnixTimestamp(str(start))
            data.append((timestamp + delayAfterHatch * 60, RaidLocation(latitude, longitude)))

        log.debug("Latest Q: %s" % str(data))
        connection.commit()
        cursor.close()
        connection.close()
        return data

    def createHashDatabaseIfNotExists(self):
        log.debug('Creating hash db in database')
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False
        cursor = connection.cursor()
        query = (' Create table if not exists trshash ( ' +
                 ' hashid MEDIUMINT NOT NULL AUTO_INCREMENT, ' +
                 ' hash VARCHAR(255) NOT NULL, ' +
                 ' type VARCHAR(10) NOT NULL, ' +
                 ' id VARCHAR(255) NOT NULL, ' +
                 ' count INT(10) NOT NULL DEFAULT 1, ' +
                 ' PRIMARY KEY (hashid))')
        log.debug(query)
        cursor.execute(query)
        connection.commit()
        cursor.close()
        connection.close()
        return True

    def checkForHash(self, imghash, type, raidNo):
        log.debug(
            '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'checkForHash: Checking for hash in db')
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return None
        cursor = connection.cursor()

        query = (' SELECT  id, BIT_COUNT( ' +
                 ' CONV(hash, 16, 10) ^ CONV(\'' + str(imghash) + '\', 16, 10) ' +
                 ' ) as hamming_distance, type ' +
                 ' FROM trshash ' +
                 ' HAVING hamming_distance < 4 and type = \'' + str(type) + '\'' +
                 ' ORDER BY hamming_distance ASC')

        # query = (' SELECT  id, type ' +
        #         ' FROM trshash ' +
        #         ' where hash = \'' + str(imghash) + '\' and type = \'' + str(type) + '\'')       

        # query = (' SELECT id FROM trshash ' +
        # 'WHERE type = \'%s\' and hash = \'%s\''
        # % (str(type), str(hash)))

        cursor.execute(query)
        id = None
        data = cursor.fetchall()
        number_of_rows = cursor.rowcount
        cursor.close()
        connection.close()

        log.debug('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'checkForHash: Found Hashes in Database: %s' % str(number_of_rows))
        if number_of_rows > 0:
            log.debug(
                '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'checkForHash: Returning found ID')
            for row in data:
                log.debug(
                    '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'checkForHash: ID: ' + str(row[0]))
                return True, row[0]
        else:
            log.debug(
                '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'checkForHash: No matching Hash found')
            return False, None

    def insertHash(self, imghash, type, id, raidNo):
        doubleCheck = self.checkForHash(imghash, type, raidNo)
        if doubleCheck[0]:
            log.debug('[Crop: ' + str(raidNo) + ' (' + str(
                self.uniqueHash) + ') ] ' + 'insertHash: Already in DB - update Counter')
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False
        cursor = connection.cursor()
        if not doubleCheck[0]:
            query = (' INSERT INTO trshash ' +
                     ' ( hash, type, id ) VALUES ' +
                     ' (\'%s\', \'%s\', \'%s\')'
                     % (str(imghash), str(type), str(id)))
        else:
            query = (' UPDATE trshash ' +
                     ' set count=count+1 '
                     ' where hash=\'%s\''
                     % (str(imghash)))

        cursor.execute(query)
        connection.commit()

        cursor.close()
        connection.close()
        return True

    def deleteHashTable(self, ids, type):
        log.debug('Deleting old Hashes of type %s' % type)
        log.debug('Valid ids: %s' % ids)
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False
        cursor = connection.cursor()
        query = (' DELETE FROM trshash ' +
                 ' where id not in (' + ids + ') ' +
                 ' and type like \'%' + type + '%\'')
        log.debug(query)
        cursor.execute(query)
        connection.commit()

        cursor.close()
        connection.close()
        return True

    def submitRaid(self, gym, pkm, lvl, start, end, type, raidNo, captureTime, MonWithNoEgg=False):
        log.debug('[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'submitRaid: Submitting raid')
        zero = datetime.datetime.now()
        zero = time.mktime(zero.timetuple()) - (self.timezone * 60 * 60)
        now_timezone = datetime.datetime.fromtimestamp(float(captureTime))
        now_timezone = time.mktime(now_timezone.timetuple()) - (self.timezone * 60 * 60)
        now = datetime.datetime.now()
        date1 = str(now.year) + "-0" + str(now.month) + "-" + str(now.day)
        today1 = date1 + " " + str(now.hour - (self.timezone)) + ":" + str(now.minute) + ":" + str(now.second)

        if self.raidExist(gym, type, raidNo, pkm):
            self.refreshTimes(gym, raidNo, captureTime)
            log.debug('[Crop: ' + str(raidNo) + ' (' + str(
                self.uniqueHash) + ') ] ' + 'submitRaid: %s already submitted - ignoring' % str(type))
            return False

        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        wh_send = False

        if start is not None:
            start = start - self.timezone * 60 * 60
        if end is not None:
            end = end - self.timezone * 60 * 60

        cursor = connection.cursor()
        log.debug('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'submitRaid: Submitting something of type %s' % type)
        if type == 'EGG':
            # query = " UPDATE raid SET level = %s, spawn=FROM_UNIXTIME(%s), start=FROM_UNIXTIME(%s),
            # end=FROM_UNIXTIME(%s), pokemon_id = %s, cp = %s, move_1 = %s, move_2 = %s, last_scanned = %s WHERE
            # gym_id = %s " data = (lvl, start, start, end, monegg[int(lvl) - 1], "999", "1", "1",  today1, guid)
            log.info("Submitting Egg. Gym: %s, Lv: %s, Start and Spawn: %s, End: %s, last_scanned: %s" % (
            gym, lvl, start, end, today1))
            query = (' INSERT INTO raid (gym_id, level, spawn, start, end, pokemon_id, cp, move_1, ' +
                     'move_2, last_scanned) VALUES(%s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s), ' +
                     'FROM_UNIXTIME(%s), %s, %s, %s, %s, FROM_UNIXTIME(%s)) ON DUPLICATE KEY UPDATE level = %s, ' +
                     'spawn=FROM_UNIXTIME(%s), start=FROM_UNIXTIME(%s), end=FROM_UNIXTIME(%s), ' +
                     'pokemon_id = %s, cp = %s, move_1 = %s, move_2 = %s, last_scanned = FROM_UNIXTIME(%s)')
            data = (gym, lvl, start, start, end, None, "999", "1", "1", now_timezone,  # TODO: check None vs null?
                    lvl, start, start, end, None, "999", "1", "1", now_timezone)

            cursor.execute(query, data)

            wh_send = True
            wh_start = start
            wh_end = end
            pkm = 0

        else:
            log.info('[Crop: ' + str(raidNo) + ' (' + str(
                self.uniqueHash) + ') ] ' + 'submitRaid: Submitting mon. PokemonID %s, Lv %s, last_scanned %s, gymID %s' % (
                     pkm, lvl, today1, gym))
            if not MonWithNoEgg:
                query = " UPDATE raid SET level = %s, pokemon_id = %s, cp = %s, move_1 = %s, move_2 = %s, last_scanned = FROM_UNIXTIME(%s) WHERE gym_id = %s "
                data = (lvl, pkm, "999", "1", "1", now_timezone, gym)

                foundEndTime, EndTime = self.getRaidEndtime(gym, raidNo)

                if foundEndTime:
                    wh_send = True
                    wh_start = int(EndTime) - 2700
                    wh_end = EndTime
                else:
                    wh_send = False

            else:
                query = (' INSERT INTO raid (gym_id, level, spawn, start, end, pokemon_id, cp, move_1, ' +
                         'move_2, last_scanned) VALUES(%s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s), ' +
                         'FROM_UNIXTIME(%s), %s, %s, %s, %s, FROM_UNIXTIME(%s)) ON DUPLICATE KEY UPDATE level = %s, ' +
                         'spawn=FROM_UNIXTIME(%s), start=FROM_UNIXTIME(%s), end=FROM_UNIXTIME(%s), ' +
                         'pokemon_id = %s, cp = %s, move_1 = %s, move_2 = %s, last_scanned = FROM_UNIXTIME(%s)')
                data = (gym, lvl, int(zero) - 10000, int(zero) - 10000, end, pkm, "999", "1", "1", now_timezone,
                        # TODO: check None vs null?
                        lvl, int(zero) - 10000, int(zero) - 10000, end, pkm, "999", "1", "1", now_timezone)

                wh_send = True
                wh_start = int(end) - 2700
                wh_end = end

            cursor.execute(query, data)

        connection.commit()
        cursor.close()
        connection.close()

        log.info('[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'submitRaid: Submit finished')
        self.refreshTimes(gym, raidNo, captureTime)

        if args.webhook and wh_send:
            log.info('[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'submitRaid: Send webhook')
            send_webhook(gym, 'RAID', wh_start, wh_end, lvl, pkm)

        return True

    def readRaidEndtime(self, gym, raidNo):
        log.debug('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'readRaidEndtime: Check DB for existing mon')
        now = (datetime.datetime.now() - datetime.timedelta(hours=self.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        cursor = connection.cursor()
        query = (' SELECT raid.end FROM raid ' +
                 ' WHERE STR_TO_DATE(raid.end,\'%Y-%m-%d %H:%i:%s\') >= STR_TO_DATE(\'' + str(
                    now) + '\',\'%Y-%m-%d %H:%i:%s\') and gym_id = \'' + str(gym) + '\'')
        cursor.execute(query)
        data = cursor.fetchall()
        number_of_rows = cursor.rowcount
        cursor.close()
        connection.close()
        if number_of_rows > 0:
            for row in data:
                log.debug('[Crop: ' + str(raidNo) + ' (' + str(
                    self.uniqueHash) + ') ] ' + 'readRaidEndtime: Found Rows: %s' % str(number_of_rows))
                log.info('[Crop: ' + str(raidNo) + ' (' + str(
                    self.uniqueHash) + ') ] ' + 'readRaidEndtime: Endtime already submitted')
                return True

        log.info('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'readRaidEndtime: Endtime is new - submitting')
        return False

    def getRaidEndtime(self, gym, raidNo):
        log.debug('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'getRaidEndtime: Check DB for existing mon')
        now = (datetime.datetime.now() - datetime.timedelta(hours=self.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        cursor = connection.cursor()
        query = (' SELECT UNIX_TIMESTAMP(raid.end) FROM raid ' +
                 ' WHERE STR_TO_DATE(raid.end,\'%Y-%m-%d %H:%i:%s\') >= STR_TO_DATE(\'' + str(
                    now) + '\',\'%Y-%m-%d %H:%i:%s\') and gym_id = \'' + str(gym) + '\'')

        cursor.execute(query)
        data = cursor.fetchall()
        number_of_rows = cursor.rowcount
        cursor.close()
        connection.close()
        if number_of_rows > 0:
            for row in data:
                log.debug('[Crop: ' + str(raidNo) + ' (' + str(
                    self.uniqueHash) + ') ] ' + 'getRaidEndtime: Returning found endtime')
                log.debug(
                    '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'getRaidEndtime: Time: ' + str(
                        row[0]))
                return True, row[0]

        log.debug('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'getRaidEndtime: No matching endtime found')

        return False, None

    def raidExist(self, gym, type, raidNo, mon=0):
        log.debug(
            '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Check DB for existing entry')
        now = (datetime.datetime.now() - datetime.timedelta(hours=self.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        if type == "EGG":
            log.debug('[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Check for EGG')
            cursor = connection.cursor()
            query = (' SELECT start FROM raid ' +
                     ' WHERE STR_TO_DATE(raid.start,\'%Y-%m-%d %H:%i:%s\') >= STR_TO_DATE(\'' + str(
                        now) + '\',\'%Y-%m-%d %H:%i:%s\') and gym_id = \'' + str(gym) + '\'')
            log.debug(query)
            cursor.execute(query)
            data = cursor.fetchall()
            number_of_rows = cursor.rowcount
            if number_of_rows > 0:
                log.debug(
                    '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Found Rows: %s' % str(
                        number_of_rows))
                log.info('[Crop: ' + str(raidNo) + ' (' + str(
                    self.uniqueHash) + ') ] ' + 'raidExist: Egg already submitted - ignore new entry')
                return True

            log.info(
                '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Egg is new - submitting')
            return False
        else:
            log.debug('[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Check for Mon')
            cursor = connection.cursor()
            query = (' SELECT start FROM raid ' +
                     ' WHERE STR_TO_DATE(raid.start,\'%Y-%m-%d %H:%i:%s\') <= STR_TO_DATE(\'' + str(
                        now) + '\',\'%Y-%m-%d %H:%i:%s\') and STR_TO_DATE(raid.end,\'%Y-%m-%d %H:%i:%s\') >= STR_TO_DATE(\'' + str(
                        now) + '\',\'%Y-%m-%d %H:%i:%s\') and gym_id = \'' + str(gym) + '\' and pokemon_id=' + str(mon))
            log.debug(query)
            cursor.execute(query)
            data = cursor.fetchall()
            number_of_rows = cursor.rowcount
            cursor.close()
            connection.close()
            if number_of_rows > 0:
                log.debug(
                    '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Found Rows: %s' % str(
                        number_of_rows))
                log.info('[Crop: ' + str(raidNo) + ' (' + str(
                    self.uniqueHash) + ') ] ' + 'raidExist: Mon already submitted - ignore new entry')
                return True

            log.info(
                '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'raidExist: Mon is new - submitting')
            return False

    def refreshTimes(self, gym, raidNo, captureTime):
        log.debug('[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'Refresh Gym Times')
        now = (datetime.datetime.fromtimestamp(float(captureTime)) - datetime.timedelta(hours=self.timezone)).strftime(
            "%Y-%m-%d %H:%M:%S")
        now_timezone = datetime.datetime.fromtimestamp(float(captureTime))
        now_timezone = time.mktime(now_timezone.timetuple()) - (self.timezone * 60 * 60)
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        cursor = connection.cursor()
        query = (' update gym ' +
                 ' set last_modified = \'' + str(now) + '\', last_scanned = \'' + str(
                    now) + '\' where gym_id = \'' + gym + '\'')
        cursor.execute(query)
        query = (' update raid ' +
                 ' set last_scanned = FROM_UNIXTIME(\'' + str(now_timezone) + '\') where gym_id = \'' + gym + '\'')
        cursor.execute(query)
        connection.commit()
        cursor.close()
        connection.close()
        return True

    def getNearGyms(self, lat, lng, hash, raidNo):
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return []
        cursor = connection.cursor()
        # query = (' SELECT start, latitude, longitude FROM raid LEFT JOIN gym ' +
        #    'ON raid.gym_id = gym.gym_id WHERE raid.start >= \'%s\''
        #    % str(datetime.datetime.now() - datetime.timedelta(hours = self.timezone)))

        query = ('SELECT ' +
                 ' gym_id, ( ' +
                 ' 6371 * acos ( ' +
                 ' cos ( radians( \'' + str(lat) + '\' ) ) ' +
                 ' * cos( radians( latitude ) ) ' +
                 ' * cos( radians( longitude ) - radians( \'' + str(lng) + '\' ) ) ' +
                 ' + sin ( radians( \'' + str(lat) + '\' ) ) ' +
                 ' * sin( radians( latitude ) ) ' +
                 ' ) ' +
                 ' ) AS distance ' +
                 ' FROM gym ' +
                 ' HAVING distance <= 2 ' +
                 ' ORDER BY distance')

        cursor.execute(query)

        data = []
        log.debug('[Crop: ' + str(raidNo) + ' (' + str(
            self.uniqueHash) + ') ] ' + 'getNearGyms: Result of NearGyms query: %s' % str(query))
        for (gym_id) in cursor:
            data.append(gym_id)

        log.debug(
            '[Crop: ' + str(raidNo) + ' (' + str(self.uniqueHash) + ') ] ' + 'getNearGyms: Closest Gyms: %s' % str(
                data))
        connection.commit()
        cursor.close()
        connection.close()
        return data

    def setScannedLocation(self, lat, lng, captureTime):

        now = (datetime.datetime.fromtimestamp(float(captureTime)) - datetime.timedelta(hours=self.timezone)).strftime(
            "%Y-%m-%d %H:%M:%S")
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        cursor = connection.cursor()
        query = (
                    'insert into scannedlocation (cellid, latitude, longitude, last_modified, done, band1, band2, '
                    'band3, band4, band5, midpoint, width) values ' +
                    '(' + str(
                time.time()) + ', ' + lat + ', ' + lng + ', \'' + now + '\', 1, -1, -1, -1, -1, -1, -1, -1)')
        cursor.execute(query)

        connection.commit()
        cursor.close()
        connection.close()
        return True

    def downloadDbCoords(self):
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False
        log.info('Downloading coords')
        lll = args.latlngleft
        llr = args.latlngright
        queryStr = ""
        if lll and llr:
            queryStr = ' where (latitude BETWEEN {} AND {}) AND (longitude BETWEEN {} AND {})'.format(lll[0], llr[0],
                                                                                                      lll[1], llr[1])
        query = "SELECT latitude, longitude FROM gym {}".format(queryStr)
        cursor = connection.cursor()
        cursor.execute(query)
        file = open(args.file, 'w')
        for (latitude, longitude) in cursor:
            file.write(str(latitude) + ', ' + str(longitude) + '\n')
        cursor.close()
        connection.close()
        file.close()
        log.info('Downloading finished.')
        return True

    def __encodeHashJson(self, team_id, latitude, longitude, name, description, url):
        return ({'team_id': team_id, 'latitude': latitude, 'longitude': longitude, 'name': name, 'description': '', 'url': url})

    def __download_img(self, url, file_name):
        retry = 1
        while retry <= 5:
            try:
                r = requests.get(url, stream=True, timeout=5)
                if r.status_code == 200:
                    with open(file_name, 'wb') as f:
                        r.raw.decode_content = True
                        shutil.copyfileobj(r.raw, f)
                    break
            except KeyboardInterrupt:
                log.info('Ctrl-C interrupted')
                sys.exit(1)
            except:
                retry = retry + 1
                log.info('Download error', url)
                if retry <= 5:
                    log.info('retry:', retry)
                else:
                    log.info('Failed to download after 5 retry')

    def downloadGymImages(self):
        try:
            connection = mysql.connector.connect(host=self.host,
                                                 user=self.user, port=self.port, passwd=self.password,
                                                 db=self.database)
        except:
            log.error("Could not connect to the SQL database")
            return False

        import json
        import io
        import os
        gyminfo = {}

        url_image_path = os.getcwd() + '/gym_img/'
        file_path = os.path.dirname(url_image_path)
        if not os.path.exists(file_path):
            os.makedirs(file_path)

        query = "SELECT gym.gym_id, gym.team_id, gym.latitude, gym.longitude, gymdetails.name, " \
                "gymdetails.description, gymdetails.url FROM gym inner join gymdetails where gym.gym_id = " \
                "gymdetails.gym_id "
        cursor = connection.cursor()
        cursor.execute(query)

        for (gym_id, team_id, latitude, longitude, name, description, url) in cursor:
            if url is not None:
                filename = url_image_path + '_' + str(gym_id) + '_.jpg'
                print('Downloading', filename)
                self.__download_img(str(url), str(filename))
                gyminfo[gym_id] = self.__encodeHashJson(team_id, latitude, longitude, name, description, url)
        cursor.close()
        connection.close()
        with io.open('gym_info.json', 'w', encoding='UTF-8') as outfile:
            outfile.write(unicode(json.dumps(gyminfo, indent=4, sort_keys=True)))
        return True
