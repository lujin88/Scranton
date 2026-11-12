import wrapper


def test_signature_ignores_timers_and_spinners():
    a = "● [22:41:09] cat << 'EOF' > out.md ... running\nesc to cancel · 1 task(s)\n✻ Working… (12m 03s)"
    b = "● [22:41:09] cat << 'EOF' > out.md ... running\nesc to cancel · 1 task(s)\n✶ Working… (47m 51s)"
    assert wrapper._stuck_signature(a) == wrapper._stuck_signature(b)
    c = a + "\nwrote 120 lines"
    assert wrapper._stuck_signature(a) != wrapper._stuck_signature(c)


def test_thresholds():
    assert wrapper.STUCK_TELL == 30 and wrapper.STUCK_ESC == 60
