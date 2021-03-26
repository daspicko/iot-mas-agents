# - *- coding: utf- 8 - *-
def secondsToHumanTime(seconds):
    d = seconds / (24 * 60 * 60)
    seconds %= (24 * 60 * 60)
    h = seconds / (60 * 60)
    seconds %= (60 * 60)
    m = seconds / 60
    seconds %= 60
    s = seconds

    dText = f"{d} dana " if d > 0 else ""
    hText = f"{h} sati " if h > 0 else ""
    mText = f"{m} minuta " if m > 0 else ""
    sText = f"{s} sekundi" if s > 0 else ""
    return f"{dText}{hText}{mText}{sText}"