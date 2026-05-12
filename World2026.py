import io
import os
import textwrap

import cairosvg
from datetime import date, timedelta
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import ImageFilter
from PIL import ImageChops
import numpy as np
import pandas as pd
import locale
import pytz
import pycountry
import gettext

LANG = 'ru'  # de, en, es, fr, it, ru
tz_host = pytz.timezone('US/Eastern')
tz_local = pytz.timezone('Europe/Moscow')
late_offset = pd.Timedelta(hours=1)  # For including late-evening matches into current day

dpi = 300
# resample = 1
# mm
margin = 5
width = 297 - margin * 2
height = 210 - margin * 2

# Grid
GRID_XN = 9
GRID_YN = 6
CALENDAR_AT = (1, 0)

DRAW_MATCH_SCALE = 0.75

GROUPS_LOCATION = 1  # 0 - Horizontal at bottom, 1 - Vertical


def mm2px(mm):
    return round(mm * dpi / 25.4)


def grid2pxX(x, n=GRID_XN):
    return round(imageW * x / n)


def grid2pxY(y, n=GRID_YN):
    return round(imageH * y / n)


def grid2px(x, y):
    return grid2pxX(x), grid2pxY(y)


# px
imageW = mm2px(width)
imageH = mm2px(height)

#
L1 = grid2pxY(0.005)

# Colors
C0 = (0x00, 0x00, 0x00)  # Black
C1 = (0xED, 0xF6, 0xEF)  # Light Green
C2 = (0xFF, 0xEC, 0xEC)  # Light Red
C3 = (0xC1, 0xE2, 0xC7)  # Green
C4 = (0xD4, 0xD4, 0xD4)  # Light Grey
C5 = (0xE3, 0xC1, 0xC1)  # Red
C6 = (0x16, 0x64, 0xA2)  # Blue
C7 = (0x80, 0x80, 0x80)  # Grey
CW = (0xFF, 0xFF, 0xFF)  # White
CG = {  #   H   S   B
    'A': (0x02, 0xE5, 0x77),  # 151  99  90
    'B': (0xFE, 0x18, 0x44),  # 349  91  99
    'C': (0xFD, 0x91, 0x04),  #  34  98  99
    'D': (0x39, 0x54, 0xFA),  # 232  77  98
    'E': (0x62, 0x01, 0xE8),  # 265  99  91
    'F': (0xC6, 0xFF, 0x04),  #  74  98 100
    'G': (0xF0, 0x62, 0x93),  # 339  59  94
    'H': (0x64, 0xFE, 0xDA),  # 166  61  99
    'I': (0xAB, 0x48, 0xBC),  # 291  62  74
    'J': (0x30, 0x74, 0x85),  # 192  64  52
    'K': (0xFC, 0x3F, 0x03),  #  14  99  99
    'L': (0x48, 0xB6, 0xEB),  # 200  69  92
}


class Data:
    def __init__(self):
        self.load_matches()
        self.load_teams()
        self.num_of_weeks = self.end_date.isocalendar()[1] - self.start_date.isocalendar()[1] + 1
        pass

    def load_matches(self):
        self.matches = pd.read_excel('World2026\\WCup_2026_4.2.5_en.xlsx', sheet_name='Matches', skiprows=3, header=None, usecols='B:E,G:J')
        self.matches.columns = ['MatchNo', 'Team1', 'Team2', 'DateTimeLocalHost', 'VenueNo', 'Venue', 'Team1Name', 'Team2Name']
        dt_host = pd.to_datetime(self.matches['DateTimeLocalHost'])
        self.matches['DateTimeLocalHost'] = dt_host.dt.tz_localize(tz_host)
        self.matches['DateTime'] = self.matches['DateTimeLocalHost'].dt.tz_convert(tz_local)
        condition = self.matches['Team1'].isna()
        self.matches['Phase'] = np.where(condition, self.matches['MatchNo'], np.nan)
        self.matches['Phase'] = self.matches['Phase'].ffill()
        self.matches = self.matches.dropna(subset=['Team1'])
        self.start_date = self.matches['DateTimeLocalHost'].min().date()
        self.end_date = self.matches['DateTimeLocalHost'].max().date()
        # self.matches['DayNo'] = self.matches['DateTimeLocalHost'].dt.date.apply(self.date2dayno)

        shifted_dates = (self.matches['DateTimeLocalHost'] - late_offset).dt.date
        self.matches['DayNo'] = (shifted_dates - self.start_date).apply(lambda x: x.days + 1)

        self.matches_by_day = self.matches.groupby('DayNo')
        self.days = pd.date_range(self.start_date, self.end_date).to_frame(index=False, name='d')
        self.days.index += 1

    def load_teams(self):
        self.teams = pd.read_excel('World2026\\WCup_2026_4.2.5_en.xlsx', sheet_name='Groups', skiprows=3, usecols='B,D')
        self.teams.dropna(inplace=True)
        self.teams['GroupLetter'] = [x[0] for x in self.teams.Team]
        self.teams_by_group = self.teams.groupby('GroupLetter')

    def date2dayno(self, d):
        if isinstance(d, date) and not pd.isnull(d):
            return (d - self.start_date).days + 1

    def dayno2date(self, n):
        return self.start_date + timedelta(days=int(n) - 1)


class Lang:
    def __init__(self):
        locale.setlocale(locale.LC_ALL, LANG)
        self.countries = pd.read_json('Lang/countries.json').set_index('alpha2')
        self.simple_countries = pd.read_json('Lang/simple_countries.json').set_index('alpha2')
        self.venues = pd.read_excel('World2026/venues.xlsx').set_index('en')
        self.captions = pd.read_excel('Lang/captions.xlsx').set_index('caption')

    def _translate(self, df, key, default_value):
        try:
            value = df.at[key, LANG]
            if pd.isna(value):
                return default_value
            return value
        except KeyError:
            return default_value

    def get_country(self, code):
        r = self._translate(self.simple_countries, code, '')
        if r == '':
            r = self._translate(self.countries, code, code)
        return r

    def get_venue(self, venue):
        return self._translate(self.venues, venue, venue)

    def get_caption(self, caption):
        return self._translate(self.captions, caption, caption)


class Flags:
    COUNTRY_MAP = {
        "Rep. of Korea": "South Korea",
        "Czech Rep.": "Czech Republic",
        "Bosnia/Herzeg.": "Bosnia and Herzegovina",
        "USA": "United States of America",
        "Turkey": "Türkiye",
        "Ivory Coast": "Côte d'Ivoire",
        "Cape Verde": "Cabo Verde",
        "IR Iran": "Iran",
        "DR Congo": "Democratic Republic of the Congo",
    }

    def __init__(self):
        self.data_country = pd.read_json('Flags/flag-icons-main/country.json').set_index('name')

    def _get_clean_name(self, country):
        return self.COUNTRY_MAP.get(country, country)

    def _get_country_value(self, country, column):
        clean_name = self._get_clean_name(country)
        try:
            return self.data_country.at[clean_name, column]
        except KeyError:
            print(f"Warning: Country '{country}' (as '{clean_name}') not found!")
            return None

    def get_alpha2(self, country):
        return self._get_country_value(country, 'code')

    def get_flag_filename(self, country):
        return self._get_country_value(country, 'flag_4x3')


class Painter:
    def __init__(self):
        global DRAW_MATCH_SCALE
        w, h = grid2px(1, 1.25)
        DRAW_MATCH_SCALE = min(1.0, w / h)
        self.img = Image.new('RGB', (imageW, imageH), "white")
        # self.img2 = Image.new('RGB', (imageW, imageH), "white")
        self.font1 = ImageFont.truetype("SegoeWP-Bold.ttf", grid2pxY(1 * DRAW_MATCH_SCALE))  # Day
        self.font2 = ImageFont.truetype("tahomabd.ttf", grid2pxY(0.050 * DRAW_MATCH_SCALE))  # Team name
        self.font3 = ImageFont.truetype("tahoma.ttf", grid2pxY(0.044 * DRAW_MATCH_SCALE))  # Venue, Match No.
        self.font4 = ImageFont.truetype("SegoeWP-Bold.ttf", grid2pxY(0.130))  # Weekday, Month, Phase
        self.draw = ImageDraw.Draw(self.img, 'RGBA')
        # self.draw2 = ImageDraw.Draw(self.img2, 'RGBA')

    def draw_grid(self):
        # Horizontal
        for i in range(CALENDAR_AT[1] + 1, data.num_of_weeks):
            x, y = grid2px(CALENDAR_AT[0], i)
            x1 = grid2pxX(CALENDAR_AT[0] + 5)
            x2 = grid2pxX(CALENDAR_AT[0] + 7)
            line = ((x, y), (x1, y))
            self.draw.line(line, fill=C3, width=L1)
            line = ((x1, y), (x2, y))
            self.draw.line(line, fill=C5, width=L1)
        # Vertical
        start_wd = data.start_date.weekday()
        for wd in range(1, 7):
            x, y = grid2px(CALENDAR_AT[0] + wd, CALENDAR_AT[1] + 6)
            y1 = grid2pxY(CALENDAR_AT[1]) if wd > start_wd else grid2pxY(CALENDAR_AT[1] + 1)
            line = ((x, y1), (x, y))
            color = C3 if wd < 5 else C5
            self.draw.line(line, fill=color, width=L1)
        #
        self.draw.text((0, imageH), 'All times are in %s; "+" indicates the following day.' % tz_local.zone, fill=C4, font=self.font3, anchor="lb")

    def draw_days(self):
        for index, row in data.days.iterrows():
            d = row['d']
            i, j = self.date2grid(d)
            wd = d.weekday()
            x, y = grid2px(i + 0.5, j + 0.45)
            color = C1 if wd < 5 else C2
            self.draw.text((x, y), str(d.day), fill=color, font=self.font1, anchor="mm")
            # Weekday name
            if j == 1:
                color = C3 if wd < 5 else C5
                x, y = grid2px(i + 0.5, 1.12)
                self.draw.text((x, y), d.strftime("%a"), fill=color, font=self.font4, anchor="ms")
            # Month name
            if index == 1 or d.day == 1:
                x, y = grid2px(i + 0.5, j + 0.12)
                self.draw.text((x, y), d.strftime("%B"), fill=C1, font=self.font4, anchor="ms")

    def draw_logo(self):
        xc1 = grid2pxX(CALENDAR_AT[0] + 0.5)
        xc2 = grid2pxX(CALENDAR_AT[0] + 2.0)
        yc = grid2pxY(CALENDAR_AT[1] + 0.5)
        self.draw_logo_part(0.9, xc1, yc, 0, 1, 'World2026\\6642f4805a10f-FIFA-World-Cup(2).svg')
        self.draw_logo_part(2.0, xc2, yc, 0.71, 1, 'World2026\\tournaments_fifa-world-cup-2026--unofficial.football-logos.cc.svg')

    def draw_logo_part(self, s, xc, yc, ky0, ky1, url):
        h = grid2pxY(s)
        filelike_obj = io.BytesIO(cairosvg.svg2png(url=url, output_height=h))
        img = Image.open(filelike_obj)
        w = img.width
        img1 = img.crop((0, h * ky0, w, h * ky1))
        img1 = trim(img1)
        x = round(xc - img1.width / 2)
        y = round(yc - img1.height / 2)
        self.img.paste(img1, box=(x, y), mask=img1)

    def draw_matches(self):
        current_phase = np.nan
        for dayno, day_matches in data.matches_by_day:
            i, j = self.date2grid(data.dayno2date(dayno))
            xc, yc = grid2px(i + 0.5, j + 0.5)
            self.draw_day_matches(day_matches, xc, yc)
            phase = day_matches['Phase'].iat[0]
            if pd.notna(phase) and phase != '' and phase != current_phase:
                x0, y0 = grid2px(i + 0.03, j + 0.05)
                self.draw.text((x0, y0), lang.get_caption(phase), fill=C6, font=self.font4, anchor="lt")
                current_phase = phase

    def draw_day_matches(self, day_matches, xc, yc):
        day_matches.sort_values(by=['DateTime', 'MatchNo'], inplace=True)
        num = len(day_matches)
        match_row_height = 1 / (num + 0.5 * (6 - num))
        for i, yc1 in enumerate_ycs(yc, day_matches.shape[0], match_row_height):
            match = day_matches.iloc[i]
            self.draw_match(match, xc, yc1)

    def draw_match(self, match, xc, yc):
        r = grid2pxY(0.023 * DRAW_MATCH_SCALE)
        w = grid2pxY(0.093 * DRAW_MATCH_SCALE)
        h = grid2pxY(0.12 * DRAW_MATCH_SCALE)
        dx1 = grid2pxY(0.08 * DRAW_MATCH_SCALE)
        dx2 = grid2pxY(0.2 * DRAW_MATCH_SCALE)
        dx3 = grid2pxY(0.278 * DRAW_MATCH_SCALE)
        group_letter = match.Team1[0]
        # Time, Venue
        time_text = match.DateTime.time().strftime('%H:%M')
        is_next_day = match.DateTime.date() > data.dayno2date(match.DayNo)
        if is_next_day:
            time_text += "+"
        venue = time_text + ', ' + lang.get_venue(match.Venue)
        self.draw.text((xc, yc + h * 0.7), venue, fill=C0, font=self.font3, anchor="mm")
        # Group
        self.draw_group_letter(xc, yc, r, group_letter)
        # Score
        self.draw_rounded_rectangle(xc - dx1, yc, w, h, r, C4, L1)
        self.draw_rounded_rectangle(xc + dx1, yc, w, h, r, C4, L1)
        # Match No.
        self.draw.text((xc, yc - h / 2), str(match.MatchNo), fill=C4, font=self.font3, anchor="mm")
        # Teams
        if isinstance(match.Team1Name, str):
            # Team1
            self.draw_flag_and_country(self.draw, xc - dx2, yc, match.Team1Name, 'rm')
            # Team2
            self.draw_flag_and_country(self.draw, xc + dx2, yc, match.Team2Name, 'lm')
        else:
            self.draw.text((xc - dx3, yc), match.Team1, fill=C4, font=self.font2, anchor="rm")
            self.draw.text((xc + dx3, yc), match.Team2, fill=C4, font=self.font2, anchor="lm")

    def draw_circle(self, x, y, r, c):
        self.draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=c)

    def draw_flag(self, img, x, y, w, country):
        fn = flags.get_flag_filename(country)
        filelike_obj = io.BytesIO(cairosvg.svg2png(url='Flags/flag-icons-main/' + fn, output_width=w))
        imgf = Image.open(filelike_obj)
        h = imgf.height
        x0 = round(x - w / 2)
        y0 = round(y - h / 2)
        q = 2
        wb = round(w * q)
        hb = round(h * q)
        img1 = Image.new('RGBA', (wb, hb), color=(0xFF, 0xFF, 0xFF, 0x0))
        draw = ImageDraw.Draw(img1)
        draw.rectangle([(w * (q - 1) / 2, h * (q - 1) / 2), (w * ((q - 1) / 2 + 1), h * ((q - 1) / 2 + 1))], fill=C0)
        img2 = img1.filter(ImageFilter.BoxBlur(grid2pxY(0.02) * DRAW_MATCH_SCALE))

        xb = round(x - wb / 2)
        yb = round(y - hb / 2)

        img.paste(img2, box=(xb, yb), mask=img2)
        img.paste(imgf, box=(x0, y0))

    def draw_rounded_rectangle(self, xc, yc, w, h, r, c, l, f=(255, 255, 255, 128)):
        x0 = int(xc - (w + l) / 2)
        y0 = int(yc - (h + l) / 2)
        x1 = int(x0 + w + l - 1)
        y1 = int(y0 + h + l - 1)
        self.draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=r, outline=c, width=l, fill=f)

    def draw_groups(self):
        if GROUPS_LOCATION == 0:
            gn = len(data.teams_by_group)
            yc = grid2pxY(6.5)
            for i, (group_letter, teams) in enumerate(data.teams_by_group):
                x0 = grid2pxX(i + 0.15, gn)
                x1 = grid2pxX(i + 0.85, gn)
                self.draw_group(group_letter, teams, x0, x1, yc)
                # Vertical line
                if i < gn:
                    y0 = grid2pxY(6.1)
                    y1 = grid2pxY(6.9)
                    x = grid2pxX(i + 1, gn)
                    line = ((x, y0), (x, y1))
                    self.draw.line(line, fill=C4, width=L1)
        elif GROUPS_LOCATION == 1:
            for i, (group_letter, teams) in enumerate(data.teams_by_group):
                row = i % 6
                column = 0 if i < 6 else 8
                yc = grid2pxY(row + 0.5)
                x0 = grid2pxX(column + 0.07)
                x1 = grid2pxX(column + 0.93)
                self.draw_group(group_letter, teams, x0, x1, yc)
                # Horizontal line
                if row > 0:
                    x0 = grid2pxX(column + 0.2)
                    x1 = grid2pxX(column + 0.8)
                    y = grid2pxY(row)
                    line = ((x0, y), (x1, y))
                    self.draw.line(line, fill=C4, width=L1)

    def draw_group(self, group_letter, teams, x0, x1, yc):
        wf = grid2pxY(0.12)
        for i, yc1 in enumerate_ycs(yc, teams.shape[0] + 1, 0.15):
            if i == 0:
                # Header
                self.draw_group_header(group_letter, x0, x1, yc1)
            else:
                # Team
                self.draw_group_team(teams.iloc[i - 1], x0, x1, yc1, wf)
        # dy = grid2pxY(0.15)
        # yc = y + dy * 1.5
        # # for idx, yc
        # for i, team in teams.iterrows():
        #     yc = yc + dy
        #     self.draw_group_team(team, xc, yc, wf)

    def draw_group_header(self, group_letter, x0, x1, yc):
        r = grid2pxY(0.04)
        t = lang.get_caption('Group')
        font = ImageFont.truetype("tahomabd.ttf", r * 2)
        # x1 = round(xc - grid2pxX(0.4, gn))
        self.draw.text((x0, yc), t, fill=CG[group_letter], font=font, anchor="lm")
        x2 = x0 + font.getlength(t) + r * 1.5
        self.draw_group_letter(x2, yc, r, group_letter)
        w = grid2pxY(0.093)
        self.draw.text((x1 - w * 4, yc), '1', fill=C4, font=self.font3, anchor="mm")
        self.draw.text((x1 - w * 3, yc), '2', fill=C4, font=self.font3, anchor="mm")
        self.draw.text((x1 - w * 2, yc), '3', fill=C4, font=self.font3, anchor="mm")
        self.draw.text((x1 - w * 0.5, yc), lang.get_caption('Total'), fill=C4, font=self.font3, anchor="mm")

    def draw_group_team(self, team, x0, x1, yc, wf):
        r = grid2pxY(0.023)
        w = grid2pxY(0.093)
        h = grid2pxY(0.12)
        # xf = round(xc - grid2pxX(0.4, gn) + wf / 2)
        xf = round(x0 + wf / 2)
        self.draw_flag_and_country(self.draw, xf, yc, team.Name, 'lm')
        self.draw_rounded_rectangle(x1 - w * 4, yc, w, h, r, C4, L1)
        self.draw_rounded_rectangle(x1 - w * 3, yc, w, h, r, C4, L1)
        self.draw_rounded_rectangle(x1 - w * 2, yc, w, h, r, C4, L1)
        self.draw_rounded_rectangle(x1 - w * 0.5, yc, w, h, r, C4, L1)

    def draw_stickers(self):
        wf = grid2pxY(0.12 + 0.02)
        w = grid2pxY(0.5)
        h = grid2pxY(0.12)
        for i in range(4):
            xc = grid2pxX(0.5 + i)
            yc = h
            for indx, team in data.teams.iterrows():
                self.draw_flag_and_country(self.draw2, xc - wf / 2, yc, team.Name, 'rm')
                self.draw_flag_and_country(self.draw2, xc + wf / 2, yc, team.Name, 'lm')
                y0 = yc - h / 2
                y1 = yc + h / 2
                x0 = xc - w
                x1 = xc
                self.draw2.rectangle([(x0, y0), (x1, y1)], outline=C0)
                x0 = xc
                x1 = xc + w
                self.draw2.rectangle([(x0, y0), (x1, y1)], outline=C0)
                yc = yc + h

    def draw_group_letter(self, x, y, r, group_letter):
        if group_letter in CG:
            self.draw_circle(x, y, r, CG[group_letter])
            font = ImageFont.truetype("tahomabd.ttf", r * 1.8)
            y0 = round(y - r * 0.05)
            # x0 = int(x + r * 0.05) if group_letter in ['A', 'B', 'D'] else x
            self.draw.text((x, y0), group_letter, fill=CW, font=font, anchor="mm")

    def draw_flag_and_country(self, draw, xc, yc, country, anchor):
        if anchor == 'rm':
            dx = - grid2pxY(0.078 * DRAW_MATCH_SCALE)
        elif anchor == 'lm':
            dx = grid2pxY(0.078 * DRAW_MATCH_SCALE)
        else:
            return
        # Flag
        wf = grid2pxY(0.12 * DRAW_MATCH_SCALE)
        self.draw_flag(draw._image, xc, yc, wf, country)
        # Country
        alpha2 = flags.get_alpha2(country)
        t = lang.get_country(alpha2)
        wrapped_text = textwrap.fill(t, width=11, break_long_words=False)
        draw.text((xc + dx, yc), wrapped_text, fill=C0, font=self.font2, anchor=anchor, align=('right' if anchor == 'rm' else 'left'))

    def save(self):
        filename = os.path.splitext(os.path.basename(__file__))[0]
        filename += "-poster-%s-%ddpi.png" % (LANG, dpi)
        print(filename)
        # if resample > 1:
        #   self.img = self.img.resize((imageW // resample, imageH // resample), resample=Image.LANCZOS)
        self.img.save("Posters\\" + filename, dpi=(dpi, dpi))
        # self.img2.save('stickers.png', dpi=(dpi, dpi))

    def date2grid(self, d):
        i = d.weekday() + CALENDAR_AT[0]
        j = d.isocalendar()[1] - data.start_date.isocalendar()[1] + CALENDAR_AT[1]
        return i, j


def trim(im):
    bg = Image.new(im.mode, im.size, im.getpixel((0, 0)))
    diff = ImageChops.difference(im, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return im.crop(bbox)


def enumerate_ycs(yc, count, h):
    ycs = []
    for i in range(count):
        ycs.append(yc + grid2pxY(h * (i + 0.5 * (1 - count))))
    return enumerate(ycs)


def main():
    painter = Painter()

    print('draw_grid')
    painter.draw_grid()
    #
    print('draw_logo')
    painter.draw_logo()
    #
    print('draw_days')
    painter.draw_days()
    #
    print('draw_matches')
    painter.draw_matches()
    #
    print('draw_groups')
    painter.draw_groups()

    # print('draw_stickers')
    # painter.draw_stickers()

    print('save')
    painter.save()


if __name__ == '__main__':
    data = Data()
    lang = Lang()
    flags = Flags()
    main()
