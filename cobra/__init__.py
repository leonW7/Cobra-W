#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    cobra
    ~~~~~

    Implements cobra main

    :author:    Feei <feei@feei.cn>
    :homepage:  https://github.com/wufeifei/cobra
    :license:   MIT, see LICENSE for more details.
    :copyright: Copyright (c) 2017 Feei. All rights reserved
"""
import sys
import time
import argparse
import logging
import traceback
from .log import log, logger
from . import cli, config
from .cli import get_sid
from .engine import Running
# from .utils import unhandled_exception_message, create_github_issue

from .__version__ import __title__, __introduction__, __url__, __version__
from .__version__ import __author__, __author_email__, __license__
from .__version__ import __copyright__, __epilog__

try:
    reload(sys)
    sys.setdefaultencoding('utf-8')
except NameError as e:
    pass


def main():
    try:
        # arg parse
        t1 = time.time()
        parser = argparse.ArgumentParser(prog=__title__, description=__introduction__, epilog=__epilog__, formatter_class=argparse.RawDescriptionHelpFormatter)

        parser_group_scan = parser.add_argument_group('Scan')
        parser_group_scan.add_argument('-t', '--target', dest='target', action='store', default='', metavar='<target>', help='file, folder, compress, or repository address')
        parser_group_scan.add_argument('-f', '--format', dest='format', action='store', default='csv', metavar='<format>', choices=['html', 'json', 'csv', 'xml'], help='vulnerability output format (formats: %(choices)s)')
        parser_group_scan.add_argument('-o', '--output', dest='output', action='store', default='', metavar='<output>', help='vulnerability output STREAM, FILE')
        parser_group_scan.add_argument('-r', '--rule', dest='special_rules', action='store', default=None, metavar='<rule_id>', help='specifies rules e.g: 1000, 1001')
        parser_group_scan.add_argument('-s', '--secret', dest='secret_name', action='store', default=None, metavar='<secret_name>', help='secret repair function e.g: wordpress')
        parser_group_scan.add_argument('-i', '--sid', dest='sid', action='store', default=None, metavar='<sid>', help='sid for cobra-wa')
        parser_group_scan.add_argument('-l', '--log', dest='log', action='store', default=None, metavar='<log>', help='log name for cobra-wa')
        parser_group_scan.add_argument('-d', '--debug', dest='debug', action='store_true', default=False, help='open debug mode')

        args = parser.parse_args()

        # log
        if args.log:
            log(logging.INFO, args.log)
        else:
            log(logging.INFO, str(time.time()))

        if args.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug('[INIT] set logging level: debug')

        if args.target is '' and args.output is '':
            parser.print_help()
            exit()

        logger.debug('[INIT] start scanning...')

        if args.sid:
            a_sid = args.sid
        else:
            a_sid = get_sid(args.target, True)

        data = {
            'status': 'running',
            'report': ''
        }
        Running(a_sid).status(data)

        cli.start(args.target, args.format, args.output, args.special_rules, a_sid, args.secret_name)

        t2 = time.time()
        logger.info('[INIT] Done! Consume Time:{ct}s'.format(ct=t2 - t1))
    except Exception as e:
        exc_msg = traceback.format_exc()
        logger.warning(exc_msg)


if __name__ == '__main__':
    main()
