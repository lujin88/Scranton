import wrapper


def test_signature_ignores_timers_and_spinners():
    a = "● [22:41:09] cat << 'EOF' > out.md ... running\nesc to cancel · 1 task(s)\n✻ Working… (12m 03s)"
    b = "● [22:41:09] cat << 'EOF' > out.md ... running\nesc to cancel · 1 task(s)\n✶ Working… (47m 51s)"
    assert wrapper._stuck_signature(a) == wrapper._stuck_signature(b)
    c = a + "\nwrote 120 lines"
    assert wrapper._stuck_signature(a) != wrapper._stuck_signature(c)


def test_signature_keeps_numeric_progress():
    """ffmpeg/wget progress is real work; stripping every digit used to treat it as stuck."""
    a = "frame=  120 fps=30 size=  1024kB time=00:00:04.00 bitrate=2034.1kbits/s"
    b = "frame= 9800 fps=30 size= 81920kB time=00:05:26.00 bitrate=2034.1kbits/s"
    assert wrapper._stuck_signature(a) != wrapper._stuck_signature(b)
    assert wrapper._stuck_signature("Downloading  9%\n") != wrapper._stuck_signature("Downloading 91%\n")


def test_thresholds():
    assert wrapper.STUCK_TELL == 30 and wrapper.STUCK_ESC == 60
