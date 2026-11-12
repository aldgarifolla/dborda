"""Запускает скрипт этапа сборки в изолированном режиме: python -I run_script.py <скрипт> <аргументы…>

С флагом -I Python не добавляет в sys.path ни текущую папку, ни папку скрипта, поэтому
файл, подложенный рядом со скриптом, не будет импортирован. Явно добавляется только
build/lib (прослойка psycopg2).
"""
import os, runpy, sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, 'lib'))
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
