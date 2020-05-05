from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import discord
from redbot.core.utils import AsyncIter


NO_IMAGE_PLACEHOLDER = (
    "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
)


async def get_img(session, url):
    async with session.get(url or NO_IMAGE_PLACEHOLDER) as resp:
        if resp.status == 200:
            img = await resp.read()
            return img
        async with session.get(NO_IMAGE_PLACEHOLDER) as resp:
            img = await resp.read()
            return img


async def charts(session, data, w, h, loc):
    fnt_file = f"{loc}/fonts/HelveticaNeueLTStd-Md.otf"
    fnt = ImageFont.truetype(fnt_file, 18, encoding="utf-8")
    imgs = []
    async for item in AsyncIter(data):
        r = await get_img(session, item[1])
        img = BytesIO(r)
        image = Image.open(img).convert("RGBA")
        draw = ImageDraw.Draw(image)
        texts = item[0].split("\n")
        if len(texts[1]) > 30:
            height = 237
            text = f"{texts[0]}\n{texts[1][:30]}\n{texts[1][30:]}"
        else:
            height = 257
            text = item[0]
        draw.text(
            (5, height),
            text,
            fill=(255, 255, 255, 255),
            font=fnt,
            stroke_width=1,
            stroke_fill=(255, 255, 255, 0),
        )
        _file = BytesIO()
        image.save(_file, "png")
        _file.name = f"{item[0]}.png"
        _file.seek(0)
        imgs.append(_file)
    return await create_graph(imgs, w, h)


async def track_chart(session, data, w, h, loc):
    fnt_file = f"{loc}/fonts/HelveticaNeueLTStd-Md.otf"
    fnt = ImageFont.truetype(fnt_file, 18, encoding="utf-8")
    imgs = []
    async for item in AsyncIter(data):
        r = await get_img(session, item[1])
        img = BytesIO(r)
        image = Image.open(img).convert("RGBA")
        draw = ImageDraw.Draw(image)
        if len(item[0]) > 30:
            height = 257
            text = f"{item[0][:30]}\n{item[0][30:]}"
        else:
            height = 277
            text = item[0]
        draw.text(
            (5, height),
            text,
            fill=(255, 255, 255, 255),
            font=fnt,
            stroke_width=1,
            stroke_fill=(255, 255, 255, 0),
        )
        _file = BytesIO()
        image.save(_file, "png")
        _file.name = f"{item[0]}.png"
        _file.seek(0)
        imgs.append(_file)
    return await create_graph(imgs, w, h)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i : i + n]


async def create_graph(data, w, h):
    dimensions = (300 * w, 300 * h)
    final = Image.new("RGBA", dimensions)
    images = chunks(data, w)
    y = 0
    async for chunked in AsyncIter(images):
        x = 0
        async for img in AsyncIter(chunked):
            new = Image.open(img)
            w, h = new.size
            final.paste(new, (x, y, x + w, y + h))
            x += 300
        y += 300
    file = BytesIO()
    final.save(file, "webp")
    file.name = f"chart.webp"
    file.seek(0)
    image = discord.File(file)
    return image
