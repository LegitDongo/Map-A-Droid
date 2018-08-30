import logging
from walkerArgs import parseArgs
import requests
import json
import datetime
import time
import sys

reload(sys)

sys.setdefaultencoding('utf8')

log = logging.getLogger(__name__)
args = parseArgs()

webhook_payload = """[{{
      "message": {{
        "latitude": {lat},
        "longitude": {lon},
        "level": {lvl},
        "pokemon_id": {poke_id},
        "team": {team},
        "cp": "{cp}",
        "move_1": {move_1},
        "move_2": {move_2},
        "raid_begin": {hatch_time},      
        "raid_end": {end},
        "gym_id": "{ext_id}",
        "name": "{name_id}",
        "gym_url": "{url}",
        "sponsor": "{sponsor}",
        "weather": "{weather}",
        "park": "{park}"
      }},
      "type": "{type}"
   }} ]"""


def get_raid_boss_cp(mon_id):
    if len(args.pokemon_json_path) > 0 & int(mon_id) > 0:
        with open(args.pokemon_json_path) as j:
            file = json.load(j)

        if file[str(mon_id)]["cp"]:
            return file[str(mon_id)]["cp"]
        else:
            log.warning("No raid cp found for " + str(mon_id))
            return '0'
    else:
        return '0'


def send_webhook(gymid, type, start, end, lvl, mon=0):
    gym_id = gymid
    move_1 = '1'
    move_2 = '1'
    cp = get_raid_boss_cp(mon)
    lvl = lvl
    poke_id = int(mon)
    hatch_time = int(start)
    end = int(end)
    form = '0'
    team = '0'
    type_ = 'raid'
    sponsor = '0'
    weather = '0'
    park = 'unknown'

    with open('gym_info.json') as f:
        data = json.load(f)

    name = 'unknown'
    lat = '0'
    lon = '0'
    url = '0'
    description = ''

    if str(gymid) in data:
        name = data[str(gymid)]["name"].replace("\\", r"\\").replace('"', '')
        lat = data[str(gymid)]["latitude"]
        lon = data[str(gymid)]["longitude"]
        url = data[str(gymid)]["url"]
        if data[str(gymid)]["description"]:
            description = data[str(gymid)]["description"].replace("\\", r"\\").replace('"', '').replace("\n", "")

        # if data[str(gymid)]["park"]:
        if 'park' in data[str(gymid)]:
            park = data[str(gymid)]["park"]

        # if data[str(gymid)]["sponsor"]:
        if 'sponsor' in data[str(gymid)]:
            sponsor = data[str(gymid)]["sponsor"]

    if args.webhook:
        payload_raw = webhook_payload.format(
            ext_id=gym_id,
            lat=lat,
            lon=lon,
            name_id=name,
            sponsor=sponsor,
            poke_id=poke_id,
            lvl=lvl,
            end=end,
            hatch_time=hatch_time,
            move_1=move_1,
            move_2=move_2,
            cp=cp,
            form=form,
            team=team,
            type=type_,
            url=url,
            description=description,
            park=park,
            weather=weather
        )

        payload = json.loads(payload_raw)
        response = requests.post(
            args.webhook_url, data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )


if __name__ == '__main__':
    send_webhook('33578092c5554275a589bd1e144bbbcc.16', 'EGG', '1534163280', '1534165980', '5', '004')
