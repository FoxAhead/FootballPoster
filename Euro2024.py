import io
import cairosvg
from datetime import date, timedelta
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import ImageFilter
from PIL import ImageChops
import pandas as pd
import locale
import pytz

# import pycountry
# import gettext

LANG = 'ru'  # de, en, es, fr, it, ru
tz_host = pytz.timezone('Europe/Berlin')
tz_local = pytz.timezone('Europe/Moscow')

dpi = 600
# resample = 1
# mm
margin = 5
width = 297 - margin * 2
height = 210 - margin * 2


def mm2px(mm):
    return round(mm * dpi / 25.4)


def grid2pxX(x, n=7):
    return round(imageW * x / n)


def grid2pxY(y, n=6):
    return round(imageH * y / n)


def grid2px(x, y):
    return grid2pxX(x), grid2pxY(y)


# px
imageW = mm2px(width)
imageH = mm2px(height)

start_date = date(2024, 6, 14)
end_date = date(2024, 7, 14)

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
CG = {
    'A': (0x5B, 0xA6, 0x6E),
    'B': (0x31, 0x48, 0x9D),
    'C': (0xC3, 0x30, 0x1F),
    'D': (0xE6, 0xB5, 0x1A),
    'E': (0x8F, 0xA9, 0xC4),  # (0x75, 0x93, 0xB5),
    'F': (0x36, 0x36, 0x3D)
}


class Data:
    def __init__(self):
        self.days = pd.date_range(start_date, end_date).to_frame(index=False, name='d')
        self.days.index += 1
        self.load_matches()
        self.load_teams()
        pass

    def load_matches(self):
        self.matches = pd.read_excel('EURO_2024_1.8.5_en.xlsx', sheet_name='Matches', skiprows=3, header=None, usecols='B,C,D,E,G,H,I,J')
        self.matches.rename(columns={
            1: 'MatchNo',
            2: 'Team1',
            3: 'Team2',
            4: 'DateTimeLocalHost',
            6: 'VenueNo',
            7: 'Venue',
            8: 'Team1Name',
            9: 'Team2Name',
        }, inplace=True)
        self.matches['DateTimeLocalHost'] = [d if pd.isnull(d) else tz_host.localize(d) for d in self.matches.DateTimeLocalHost]
        # self.matches['DateTimeUTC'] = [pytz.utc.localize(d) for d in self.matches.DateTimeLocalHost]
        self.matches['DateTime'] = [d if pd.isnull(d) else d.astimezone(tz_local) for d in self.matches.DateTimeLocalHost]
        self.matches['DayNo'] = [date2dayno(d.date()) for d in self.matches.DateTimeLocalHost]
        t = ''
        for index, row in self.matches.iterrows():
            self.matches.at[index, 'Phase'] = t
            if pd.isnull(row.Team1):
                t = row.MatchNo
        self.matches_by_day = self.matches.groupby('DayNo')

    def load_teams(self):
        self.teams = pd.read_excel('EURO_2024_1.8.5_en.xlsx', sheet_name='Groups', skiprows=3, usecols='B,D')
        self.teams.dropna(inplace=True)
        self.teams['GroupLetter'] = [x[0] for x in self.teams.Team]
        self.teams_by_group = self.teams.groupby('GroupLetter')


class Lang:
    def __init__(self):
        locale.setlocale(locale.LC_ALL, LANG)
        # self.translation = gettext.translation('iso3166-1', pycountry.LOCALES_DIR, languages=[LANG])
        # self.translation.install()
        self.countries = pd.read_json('Lang/countries.json')
        # self.venues = pd.read_json('Lang/venues.json')
        self.venues = pd.read_excel('Lang/venues.xlsx')
        self.captions = pd.read_excel('Lang/captions.xlsx')

    def get_country(self, code):
        # c = pycountry.countries.get(alpha_2=code)
        # if c is not None:
        #     return _(c.name)
        # c = pycountry.subdivisions.get(code=code)
        # if c is not None:
        #     return _(c.name)
        # return code

        df = self.countries.loc[self.countries.alpha2 == code]
        if df.empty:
            return code
        return df.iloc[0][LANG]

    def get_venue(self, venue):
        df = self.venues.loc[self.venues.en == venue]
        if df.empty:
            return venue
        return df.iloc[0][LANG]

    def get_caption(self, caption):
        df = self.captions.loc[self.captions.caption == caption]
        if df.empty:
            return caption
        return df.iloc[0][LANG]


class Flags:
    def __init__(self):
        self.data_country = pd.read_json('Flags/country.json')

    def get_alpha2(self, country):
        row = self.data_country.loc[self.data_country.name == country].iloc[0]
        return row.code

    def get_flag_filename(self, country):
        row = self.data_country.loc[self.data_country.name == country].iloc[0]
        return row.flag_4x3


class Painter:
    def __init__(self):
        self.img = Image.new('RGB', (imageW, imageH), "white")
        self.img2 = Image.new('RGB', (imageW, imageH), "white")
        self.font1 = ImageFont.truetype("SegoeWP-Bold.ttf", grid2pxY(1))  # Day
        self.font2 = ImageFont.truetype("tahomabd.ttf", grid2pxY(0.050))  # Team name
        self.font3 = ImageFont.truetype("tahoma.ttf", grid2pxY(0.044))  # Venue, Match No.
        self.font4 = ImageFont.truetype("SegoeWP-Bold.ttf", grid2pxY(0.150))  # Weekday, Month, Phase
        self.draw = ImageDraw.Draw(self.img, 'RGBA')
        self.draw2 = ImageDraw.Draw(self.img2, 'RGBA')

    def draw_grid(self):
        # Horizontal
        for i in range(4):
            x, y = grid2px(0, i + 1)
            x1 = grid2pxX(5)
            line = ((0, y), (x1, y))
            self.draw.line(line, fill=C3, width=L1)
            line = ((x1, y), (imageW, y))
            self.draw.line(line, fill=C5, width=L1)
        # Vertical
        for i in range(6):
            x, y = grid2px(i + 1, 5)
            y0 = 0 if i > 2 else grid2pxY(1)
            line = ((x, y0), (x, y))
            color = C3 if i < 4 else C5
            self.draw.line(line, fill=color, width=L1)

    def draw_days(self):
        for index, row in data.days.iterrows():
            d = row['d']
            i, j = date2grid(d)
            x, y = grid2px(i + 0.5, j + 0.45)
            color = C1 if i < 5 else C2
            self.draw.text((x, y), str(d.day), fill=color, font=self.font1, anchor="mm")
            # Weekday name
            if j == 1:
                color = C3 if i < 5 else C5
                x, y = grid2px(i + 0.5, 1.12)
                self.draw.text((x, y), d.strftime("%a"), fill=color, font=self.font4, anchor="ms")
            # Month name
            if index == 1 or d.day == 1:
                x, y = grid2px(i + 0.5, j + 0.12)
                self.draw.text((x, y), d.strftime("%B"), fill=C1, font=self.font4, anchor="ms")

    def draw_logo(self):
        xc1 = grid2pxX(1)
        xc2 = grid2pxX(2.5)
        yc = grid2pxY(0.5)
        self.draw_logo_part(1.6, xc1, yc, 0, 0.6)
        self.draw_logo_part(2.5, xc2, yc, 0.6, 1)

    def draw_logo_part(self, s, xc, yc, ky0, ky1):
        h = grid2pxY(s)
        filelike_obj = io.BytesIO(cairosvg.svg2png(url='UEFA_Euro_2024_Logo.svg', output_height=h))
        img = Image.open(filelike_obj)
        w = img.width
        img1 = img.crop((0, h * ky0, w, h * ky1))
        img1 = trim(img1)
        x = round(xc - img1.width / 2)
        y = round(yc - img1.height / 2)
        self.img.paste(img1, box=(x, y), mask=img1)

    def draw_matches(self):
        for dayno, day_matches in data.matches_by_day:
            i, j = date2grid(dayno2date(dayno))
            xc, yc = grid2px(i + 0.5, j + 0.5)
            self.draw_day_matches(day_matches, xc, yc)
            # Phase
            p = day_matches.iloc[0].Phase
            if p != '':
                x0, y0 = grid2px(i + 0.03, j + 0.05)
                self.draw.text((x0, y0), lang.get_caption(p), fill=C6, font=self.font4, anchor="lt")

    def draw_day_matches(self, day_matches, xc, yc):
        day_matches.sort_values(by=['DateTime', 'MatchNo'], inplace=True)
        for i, yc1 in enumerate_ycs(yc, day_matches.shape[0], 0.25):
            match = day_matches.iloc[i]
            self.draw_match(match, xc, yc1)

    def draw_match(self, match, xc, yc):
        r = grid2pxY(0.023)
        w = grid2pxY(0.093)
        h = grid2pxY(0.12)
        # wf = grid2pxY(0.12)
        dx1 = grid2pxY(0.08)
        dx2 = grid2pxY(0.2)
        dx3 = grid2pxY(0.278)
        group_letter = match.Team1[0]
        # Venue
        venue = match.DateTime.time().strftime('%H:%M') + ', ' + lang.get_venue(match.Venue)
        self.draw.text((xc, yc + h * 0.8), venue, fill=C0, font=self.font3, anchor="mm")
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
        filelike_obj = io.BytesIO(cairosvg.svg2png(url='Flags/' + fn, output_width=w))
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
        img2 = img1.filter(ImageFilter.BoxBlur(grid2pxY(0.02)))

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
        gn = len(data.teams_by_group)
        yc = grid2pxY(5.5)
        for i, (group_letter, teams) in enumerate(data.teams_by_group):
            x0 = grid2pxX(i + 0.15, gn)
            x1 = grid2pxX(i + 0.85, gn)
            self.draw_group(group_letter, teams, x0, x1, yc)
            # Vertical line
            if i < gn:
                y0 = grid2pxY(5.1)
                y1 = grid2pxY(5.9)
                x = grid2pxX(i + 1, gn)
                line = ((x, y0), (x, y1))
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
        x2 = x0 + font.getlength(t) + r * 2
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
            dx = - grid2pxY(0.078)
        elif anchor == 'lm':
            dx = grid2pxY(0.078)
        else:
            return
        wf = grid2pxY(0.12)
        alpha2 = flags.get_alpha2(country)
        t = lang.get_country(alpha2)
        self.draw_flag(draw._image, xc, yc, wf, country)
        draw.text((xc + dx, yc), t, fill=C0, font=self.font2, anchor=anchor)

    def save(self):
        # if resample > 1:
        #   self.img = self.img.resize((imageW // resample, imageH // resample), resample=Image.LANCZOS)
        # self.img.save('test.png', dpi=(dpi, dpi))
        self.img2.save('test2.png', dpi=(dpi, dpi))


def date2grid(d):
    i = d.weekday()
    j = d.isocalendar()[1] - start_date.isocalendar()[1]
    return i, j


def date2dayno(d):
    if isinstance(d, date) and not pd.isnull(d):
        return (d - start_date).days + 1


def dayno2date(n):
    return start_date + timedelta(days=n - 1)


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

    # print('draw_grid')
    # painter.draw_grid()
    #
    # print('draw_logo')
    # painter.draw_logo()
    #
    # print('draw_days')
    # painter.draw_days()
    #
    # print('draw_matches')
    # painter.draw_matches()
    #
    # print('draw_groups')
    # painter.draw_groups()

    print('draw_stickers')
    painter.draw_stickers()

    print('save')
    painter.save()


if __name__ == '__main__':
    data = Data()
    lang = Lang()
    flags = Flags()
    main()
