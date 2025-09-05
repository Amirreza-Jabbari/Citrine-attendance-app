# tests/test_attendance_calc.py
import datetime
from types import SimpleNamespace

# Paste the _calculate_all_fields body into a function we can call here,
# or import AttendanceService from your code after you've patched it.
# For simplicity, this test will use a small wrapper replicating the important parts.

def calc_from_inputs(time_in, time_out, leave_start, leave_end,
                     launch_start="14:00", launch_end="16:30", workday_hours=8, base_start="10:00"):
    # minimal local copy of the algorithm from the patched function above
    date = datetime.date(2025, 9, 5)
    dt_in = datetime.datetime.combine(date, time_in)
    dt_out = datetime.datetime.combine(date, time_out)
    if dt_out <= dt_in:
        dt_out += datetime.timedelta(days=1)
    total = int((dt_out - dt_in).total_seconds() / 60)
    # launch
    sh, sm = map(int, launch_start.split(':'))
    eh, em = map(int, launch_end.split(':'))
    launch_start_dt = datetime.datetime.combine(date, datetime.time(sh, sm))
    launch_end_dt = datetime.datetime.combine(date, datetime.time(eh, em))
    if launch_end_dt <= launch_start_dt:
        launch_end_dt += datetime.timedelta(days=1)
    overlap_start = max(dt_in, launch_start_dt)
    overlap_end = min(dt_out, launch_end_dt)
    launch_min = int((overlap_end-overlap_start).total_seconds()/60) if overlap_end>overlap_start else 0
    # leave
    ls_dt = datetime.datetime.combine(date, leave_start)
    le_dt = datetime.datetime.combine(date, leave_end)
    if le_dt <= ls_dt: le_dt += datetime.timedelta(days=1)
    overlap_start = max(dt_in, ls_dt)
    overlap_end = min(dt_out, le_dt)
    leave_min = int((overlap_end-overlap_start).total_seconds()/60) if overlap_end>overlap_start else 0
    net = max(0, total - launch_min - leave_min)
    work_minutes = workday_hours*60
    main = min(net, work_minutes)
    overtime_start = dt_in + datetime.timedelta(minutes=work_minutes)
    overtime = int((dt_out - overtime_start).total_seconds()/60) if dt_out>overtime_start else 0
    return dict(total=total, launch=launch_min, leave=leave_min, net=net, main=main, overtime=overtime)

def test_user_scenario():
    res = calc_from_inputs(datetime.time(10,0), datetime.time(20,0),
                           datetime.time(16,30), datetime.time(18,30),
                           launch_start="14:00", launch_end="16:30", workday_hours=8)
    assert res['total'] == 600
    assert res['launch'] == 150
    assert res['leave'] == 120
    assert res['net'] == 330
    assert res['main'] == 330
    assert res['overtime'] == 120
    print("All assertions passed:", res)

if __name__ == "__main__":
    test_user_scenario()
