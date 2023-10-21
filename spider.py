import logging
import os
import json

import requests
from configobj import ConfigObj
import lxml.etree as ET
from tqdm import tqdm

from modules.common import now, formatted_time
from modules.database import init_db, Release

config = ConfigObj('config.ini', encoding='utf8')


def get_new_releases() -> list[dict]:
    """
    Get releases from Surge API
    :return: list
    """
    r = requests.get(
        url=config['surge']['endpoint'] + '/mac/v5/appcast-signed-beta.xml',
        headers={
            'User-Agent': 'SurgeSpider/1.0.0',
        },
    )

    if r.status_code != 200:
        return []

    root = ET.fromstring(r.content)
    ns = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'
    new = []

    for item in root.iter('item'):
        enclosure = item.find('enclosure')
        version = enclosure.attrib.get(f'{ns}version')
        tag = enclosure.attrib.get(f'{ns}shortVersionString')
        url = enclosure.attrib.get('url')

        if not version or not tag or not url:
            continue

        version = int(version)

        if release_exists(version):
            continue

        description = item.find('markdownDescription').text or ''
        if description.startswith('<![CDATA['):
            description = description[9:-3]

        new.append({
            'version': version,
            'tag': tag,
            'url': url,
            'description': description or None,
        })

        print(f'New release: {tag} ({version})')

    new.reverse()
    return new


def release_exists(version: int) -> bool:
    """
    Check if release exists
    :param version:
    :return: bool
    """
    return Release.select().where(Release.version == version).exists()


def handle_release(version: int, tag: str, url: str, description: str = None) -> Release:
    """
    Handle release
    :param version:
    :param tag:
    :param url:
    :param description:
    :return:
    """
    release = Release.create(
        version=version,
        tag=tag,
        url=url,
        description=description,
        created_at=now(),
    )

    filename = url.split('/')[-1]
    if download_file(url, filename):
        release.filename = filename
        release.save()

    return release


def download_file(url: str, filename: str) -> bool:
    """
    Download file
    :param url:
    :param filename:
    :return: bool
    """
    if not os.path.exists('downloads'):
        os.mkdir('downloads')

    r = requests.get(url, stream=True)
    if r.status_code != 200:
        return False

    with open(f'downloads/{filename}', 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            f.write(chunk)

    return True


def send_to_telegram(release: Release):
    """
    Send release to Telegram
    :param release:
    :return:
    """
    url = config['telegram']['endpoint'] + '/bot' + config['telegram']['bot_token']
    url += '/sendDocument' if release.filename else '/sendMessage'

    message = (
        f'<b>Surge Mac v{release.tag} ({release.version})</b>\n\n'
        f'Time: <code>{formatted_time(release.created_at / 1000)}</code>\n\n'
    )

    payload = {
        'chat_id': config['telegram']['channel'],
        'parse_mode': 'HTML',
        'reply_markup': json.dumps({
            'inline_keyboard': [
                [
                    {
                        'text': 'Official Download',
                        'url': release.url,
                    }
                ]
            ]
        }, ensure_ascii=False),
        'caption' if release.filename else 'text': message
    }

    file = {
        'document': (
            f'Surge-v{release.tag}-{release.version}.zip',
            open(f'downloads/{release.filename}', 'rb')
        ),
    } if release.filename else None

    r = requests.post(
        url=url,
        files=file,
        data=payload,
    )

    if r.status_code != 200:
        print(f'Send File Failed: {r.json()}')
        return


if __name__ == '__main__':
    init_db()
    releases = get_new_releases()

    print(f'Found {len(releases)} new releases')

    for item in tqdm(releases):
        release = handle_release(**item)
        send_to_telegram(release)
