import json
import os
import sys

root = 'c:/Users/Reymart De Lara/Desktop/WinMacOS/src'
sys.path.insert(0, root)
from ui.monthly_report import MonthlyReportWidget

path = os.path.join(
    os.path.expanduser('~'),
    'OneDrive - Questronix Corporation',
    'MCSU Engineering and Hybrid Infra - Documents',
    'Projects',
    'BY',
    'RUNBOOK',
    'ASPCPU logs',
    '2026',
    'August 2026',
    'lpar_history_2026-08-30.json',
)
print('exists=', os.path.exists(path))
with open(path, 'r', encoding='utf-8') as handle:
    data = json.load(handle)

rep = MonthlyReportWidget.__new__(MonthlyReportWidget)
rep.log_data_store = {'2026-08-30': data}
report = rep._build_month_report('2026-08', 'month')
print('rows=', len(report.get('rows', [])))
for row in report.get('rows', [])[:3]:
    print(row.get('server'), row.get('metric'), row.get('month_avg'), row.get('day_map'))
