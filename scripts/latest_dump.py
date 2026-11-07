#!/usr/bin/env python3
"""Discover/download newest published IYP dump from official Apache directory listing."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ARCHIVE = 'https://archive.ihr.live/ihr/iyp/'
ROOT = Path(__file__).resolve().parents[1]
DUMPS = ROOT / 'storage' / 'dumps'


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)


def listing(url):
    with urlopen(Request(url, headers={'User-Agent': 'SmartIX-IYP/0.1'}), timeout=30) as response:
        html = response.read(200_000).decode('utf-8', errors='replace')
    p = Anchors()
    p.feed(html)
    return p.links


def latest():
    """Use YYYY/MM/DD directory naming, verify that newest day has a real dump."""
    years = sorted((x for x in listing(ARCHIVE) if re.fullmatch(r'20\d\d/', x)), reverse=True)
    for year in years:
        base_y = urljoin(ARCHIVE, year)
        months = sorted((x for x in listing(base_y) if re.fullmatch(r'(0[1-9]|1[0-2])/', x)), reverse=True)
        for month in months:
            base_m = urljoin(base_y, month)
            days = sorted((x for x in listing(base_m) if re.fullmatch(r'(0[1-9]|[12]\d|3[01])/', x)), reverse=True)
            for day in days:
                date = f'{year[:4]}-{month[:2]}-{day[:2]}'
                filename = f'iyp-{date}.dump'
                base_d = urljoin(base_m, day)
                if filename in listing(base_d):
                    return {'date': date, 'url': urljoin(base_d, filename)}
    raise RuntimeError('Nenhum dump .dump encontrado no arquivo oficial')


def download(meta):
    DUMPS.mkdir(parents=True, exist_ok=True)
    target = DUMPS / 'neo4j.dump'
    marker = DUMPS / 'downloaded.json'
    current = json.loads(marker.read_text()) if marker.exists() else {}
    if current.get('date') == meta['date'] and target.is_file() and target.stat().st_size > 0:
        print(f"Download já presente: {meta['date']}", file=sys.stderr)
        return

    partial = DUMPS / 'neo4j.dump.part'
    pending = DUMPS / '.pending-url'
    if pending.exists() and pending.read_text() != meta['url']:
        partial.unlink(missing_ok=True)
    pending.write_text(meta['url'])
    free = shutil.disk_usage(DUMPS).free
    if free < 22 * 1024**3:
        raise RuntimeError('Menos de 22 GiB livres: insuficiente até mesmo para baixar o dump recente (~19 GiB).')
    print(f"Baixando {meta['url']} (arquivo grande; suporta retomada)...", file=sys.stderr)
    subprocess.run([
        'curl', '--fail', '--location', '--retry', '3',
        '--continue-at', '-', '--output', str(partial), meta['url']
    ], check=True)
    if partial.stat().st_size < 1024 * 1024:
        raise RuntimeError('Arquivo baixado muito pequeno; não será instalado.')
    partial.replace(target)
    marker.write_text(json.dumps(meta, indent=2) + '\n')
    pending.unlink(missing_ok=True)
    print('Download concluído.', file=sys.stderr)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--date', action='store_true', help='Imprime só a data remota')
    cli.add_argument('--download', action='store_true', help='Baixa dump recente, se necessário')
    args = cli.parse_args()
    info = latest()
    if args.download:
        download(info)
    if args.date:
        print(info['date'])
    else:
        print(json.dumps(info, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(1)
