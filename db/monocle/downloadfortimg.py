import sys
import requests
import shutil
import mysql
import mysql.connector
import os
import time
import logging
import json
import io
from walkerArgs import parseArgs

log = logging.getLogger(__name__)

if not os.path.exists('gym_img'):
    log.info('gym_im directory created')
    os.makedirs('gym_img')

url_image_path = os.getcwd() + '/gym_img/'

gyminfo = {}

args = parseArgs()

try:
    log.error(args.dbip)
    log.error(args.dbusername)
    log.error(args.dbpassword)
    log.error(args.dbname)
    connection = mysql.connector.connect(host = args.dbip, user = args.dbusername, passwd = args.dbpassword, db = args.dbname)
except:
    print ("Keine Verbindung zum Server")
    exit(0)

def encodeHashJson(id, team_id, latitude, longitude, name, url, park, sponsor):
    gyminfo[id] = ({'team_id': team_id, 'latitude': latitude, 'longitude': longitude, 'name': name, 'description': '', 'url': url, 'park': park, 'sponsor': sponsor})
    

def download_img(url, file_name):
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
            print('Ctrl-C interrupted')
            session.close()
            sys.exit(1)
        except:
            retry=retry+1
            print('Download error', url)
            if retry <= 5:
                print('retry:', retry)
            else:
                print('Failed to download after 5 retry')

def main():

    file_path = os.path.dirname(url_image_path)
    if not os.path.exists(file_path):
        os.makedirs(file_path)

    query = ("SELECT forts.id, forts.lat, forts.lon, forts.name, forts.url, forts.park, forts.sponsor FROM forts")
    cursor = connection.cursor()
    cursor.execute(query)

    for (id, lat, lon, name, url, park, sponsor) in cursor:
        if url is not None:
            filename = url_image_path + '_' + str(id) + '_.jpg'
            print('Downloading', filename)
            download_img(str(url), str(filename))
            encodeHashJson(id, '0', lat, lon, name, url, park,sponsor)
    cursor.close()
    connection.close()
    with io.open('gym_info.json', 'w', encoding='UTF-8') as outfile:
        outfile.write(unicode(json.dumps(gyminfo, indent=4, sort_keys=True)))


if __name__ == '__main__':
    main()
