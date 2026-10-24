# Materials for held-out worlds

Generated from config/assets.yaml. Every item in a world is built from these.

## LJSpeech chapter LJ001 (one female reader, public domain, 22.05 kHz)

Use as `{clips: [LJ001-0025, LJ001-0026], gap: 0.6}`. LJ001-0017 to LJ001-0024 are our protected evaluation recordings.

| Clip | Seconds | Text |
|---|---:|---|
| LJ001-0001 | 9.7 | Printing, in the only sense with which we are at present concerned, differs from most if not from all the arts and crafts represented in the Exhibition |
| LJ001-0002 | 1.9 | in being comparatively modern. |
| LJ001-0003 | 9.7 | For although the Chinese took impressions from wood blocks engraved in relief for centuries before the woodcutters of the Netherlands, by a similar process |
| LJ001-0004 | 5.1 | produced the block books, which were the immediate predecessors of the true printed book, |
| LJ001-0005 | 8.1 | the invention of movable metal letters in the middle of the fifteenth century may justly be considered as the invention of the art of printing. |
| LJ001-0006 | 5.7 | And it is worth mention in passing that, as an example of fine typography, |
| LJ001-0007 | 8.4 | the earliest book printed with movable types, the Gutenberg, or "forty-two line Bible" of about fourteen fifty-five, |
| LJ001-0008 | 1.8 | has never been surpassed. |
| LJ001-0009 | 7.6 | Printing, then, for our purpose, may be considered as the art of making books by means of movable types. |
| LJ001-0010 | 8.8 | Now, as all books not primarily intended as picture-books consist principally of types composed to form letterpress, |
| LJ001-0011 | 4.5 | it is of the first importance that the letter used should be fine in form; |
| LJ001-0012 | 8.2 | especially as no more time is occupied, or cost incurred, in casting, setting, or printing beautiful letters |
| LJ001-0013 | 2.6 | than in the same operations with ugly ones. |
| LJ001-0014 | 9.9 | And it was a matter of course that in the Middle Ages, when the craftsmen took care that beautiful form should always be a part of their productions whatever they were, |
| LJ001-0015 | 9.2 | the forms of printed letters should be beautiful, and that their arrangement on the page should be reasonable and a help to the shapeliness of the letters themselves. |
| LJ001-0016 | 5.3 | The Middle Ages brought calligraphy to perfection, and it was natural therefore |
| LJ001-0017 | 7.0 | that the forms of printed letters should follow more or less closely those of the written character, and they followed them very closely. |
| LJ001-0018 | 7.5 | The first books were printed in black letter, i.e. the letter which was a Gothic development of the ancient Roman character, |
| LJ001-0019 | 6.4 | and which developed more completely and satisfactorily on the side of the "lower-case" than the capital letters; |
| LJ001-0020 | 4.7 | the "lower-case" being in fact invented in the early Middle Ages. |
| LJ001-0021 | 8.6 | The earliest book printed with movable type, the aforesaid Gutenberg Bible, is printed in letters which are an exact imitation |
| LJ001-0022 | 7.1 | of the more formal ecclesiastical writing which obtained at that time; this has since been called "missal type," |
| LJ001-0023 | 8.4 | and was in fact the kind of letter used in the many splendid missals, psalters, etc., produced by printing in the fifteenth century. |
| LJ001-0024 | 7.9 | But the first Bible actually dated (which also was printed at Maintz by Peter Schoeffer in the year fourteen sixty-two) |
| LJ001-0025 | 8.9 | imitates a much freer hand, simpler, rounder, and less spiky, and therefore far pleasanter and easier to read. |
| LJ001-0026 | 6.1 | On the whole the type of this book may be considered the ne-plus-ultra of Gothic type, |
| LJ001-0027 | 9.6 | especially as regards the lower-case letters; and type very similar was used during the next fifteen or twenty years not only by Schoeffer, |
| LJ001-0028 | 5.9 | but by printers in Strasburg, Basle, Paris, Lubeck, and other cities. |
| LJ001-0029 | 5.3 | But though on the whole, except in Italy, Gothic letter was most often used |
| LJ001-0030 | 6.9 | a very few years saw the birth of Roman character not only in Italy, but in Germany and France. |
| LJ001-0031 | 7.9 | In fourteen sixty-five Sweynheim and Pannartz began printing in the monastery of Subiaco near Rome, |
| LJ001-0032 | 7.1 | and used an exceedingly beautiful type, which is indeed to look at a transition between Gothic and Roman, |

## Free Spoken Digit Dataset (CC BY-SA 4.0, recorded at 8 kHz)

Six speakers saying digits: george, jackson, lucas, nicolas, theo, yweweler. Use as `{fsdd: {speaker: theo, n: 30}}` (n recordings joined, up to 50).

## Valentini read speech, speaker p287 (CC BY 4.0, 16 kHz)

Six sentences, clean or the same sentences recorded with background noise: `{valentini: clean}` or `{valentini: noisy}`.

## JFK inaugural address excerpt (public domain, 11 s, an old recording stored at 44.1 kHz)

`{jfk: true}`

## ESC-50 environmental sounds (5 s each; licence per clip as published by ESC-50)

Use as `{esc: 1-100032-A-0}`, or as noise: `{mix_noise: {esc: 1-17367-A-10, snr_db: 10}}`.

| Clip | Category | Licence |
|---|---|---|
| 1-100032-A-0 | dog | CC0-1.0 |
| 1-100038-A-14 | chirping_birds | CC-BY-3.0 |
| 1-100210-A-36 | vacuum_cleaner | CC-BY-NC-3.0 |
| 1-100210-B-36 | vacuum_cleaner | CC-BY-NC-3.0 |
| 1-101296-A-19 | thunderstorm | CC0-1.0 |
| 1-101296-B-19 | thunderstorm | CC0-1.0 |
| 1-101336-A-30 | door_wood_knock | CC-BY-NC-3.0 |
| 1-101404-A-34 | can_opening | CC-BY-3.0 |
| 1-103298-A-9 | crow | CC-BY-NC-3.0 |
| 1-103995-A-30 | door_wood_knock | CC0-1.0 |
| 1-104089-A-22 | clapping | CC-BY-3.0 |
| 1-104089-B-22 | clapping | CC-BY-3.0 |
| 1-110389-A-0 | dog | CC-BY-3.0 |
| 1-115545-A-48 | fireworks | CC-BY-3.0 |
| 1-115545-B-48 | fireworks | CC-BY-3.0 |
| 1-116765-A-41 | chainsaw | CC0-1.0 |
| 1-11687-A-47 | airplane | CC-BY-3.0 |
| 1-118206-A-31 | mouse_click | CC0-1.0 |
| 1-118559-A-17 | pouring_water | CC0-1.0 |
| 1-119125-A-45 | train | CC-BY-3.0 |
| 1-121951-A-8 | sheep | CC0-1.0 |
| 1-12653-A-15 | water_drops | CC-BY-3.0 |
| 1-12654-A-15 | water_drops | CC-BY-3.0 |
| 1-13571-A-46 | church_bells | CC-BY-NC-3.0 |
| 1-13572-A-46 | church_bells | CC-BY-NC-3.0 |
| 1-13613-A-37 | clock_alarm | CC0-1.0 |
| 1-137-A-32 | keyboard_typing | CC-BY-3.0 |
| 1-137296-A-16 | wind | CC-BY-3.0 |
| 1-14262-A-37 | clock_alarm | CC0-1.0 |
| 1-155858-A-25 | footsteps | CC0-1.0 |
| 1-155858-B-25 | footsteps | CC0-1.0 |
| 1-15689-A-4 | frog | CC-BY-3.0 |
| 1-15689-B-4 | frog | CC-BY-3.0 |
| 1-16568-A-3 | cow | CC-BY-NC-3.0 |
| 1-17092-A-27 | brushing_teeth | CC-BY-3.0 |
| 1-17092-B-27 | brushing_teeth | CC-BY-3.0 |
| 1-17124-A-43 | car_horn | CC0-1.0 |
| 1-17150-A-12 | crackling_fire | CC-BY-3.0 |
| 1-172649-A-40 | helicopter | CC0-1.0 |
| 1-172649-B-40 | helicopter | CC0-1.0 |
| 1-17295-A-29 | drinking_sipping | CC-BY-3.0 |
| 1-17367-A-10 | rain | CC0-1.0 |
| 1-17565-A-12 | crackling_fire | CC-BY-3.0 |
| 1-17585-A-7 | insects | CC-BY-3.0 |
| 1-1791-A-26 | laughing | CC-BY-3.0 |
| 1-18074-A-6 | hen | CC-BY-NC-3.0 |
| 1-18074-B-6 | hen | CC-BY-NC-3.0 |
| 1-18527-A-44 | engine | CC-BY-3.0 |
| 1-18527-B-44 | engine | CC-BY-3.0 |
| 1-18631-A-23 | breathing | CC0-1.0 |
| 1-18655-A-31 | mouse_click | CC-BY-3.0 |
| 1-187207-A-20 | crying_baby | CC0-1.0 |
| 1-18810-A-49 | hand_saw | CC-BY-3.0 |
| 1-19026-A-43 | car_horn | CC-BY-3.0 |
| 1-19111-A-24 | coughing | CC-BY-3.0 |
| 1-19118-A-24 | coughing | CC-BY-3.0 |
| 1-19501-A-7 | insects | CC-BY-3.0 |
| 1-196660-A-8 | sheep | CC-BY-3.0 |
| 1-19898-A-41 | chainsaw | CC-BY-3.0 |
| 1-20133-A-39 | glass_breaking | CC-BY-3.0 |
| 1-202111-A-3 | cow | CC0-1.0 |
| 1-20545-A-28 | snoring | CC0-1.0 |
| 1-20736-A-18 | toilet_flush | CC-BY-NC-3.0 |
| 1-208757-A-2 | pig | CC0-1.0 |
| 1-208757-B-2 | pig | CC0-1.0 |
| 1-211527-A-20 | crying_baby | CC0-1.0 |
| 1-21189-A-10 | rain | CC0-1.0 |
| 1-21896-A-35 | washing_machine | CC-BY-NC-3.0 |
| 1-21934-A-38 | clock_tick | CC-BY-3.0 |
| 1-21935-A-38 | clock_tick | CC-BY-3.0 |
| 1-23706-A-49 | hand_saw | CC-BY-3.0 |
| 1-23996-A-35 | washing_machine | CC-BY-NC-3.0 |
| 1-24796-A-47 | airplane | CC-BY-3.0 |
| 1-26143-A-21 | sneezing | CC-BY-3.0 |
| 1-26806-A-1 | rooster | CC-BY-3.0 |
| 1-27403-A-28 | snoring | CC-BY-NC-3.0 |
| 1-27724-A-1 | rooster | CC0-1.0 |
| 1-28005-A-18 | toilet_flush | CC0-1.0 |
| 1-28135-A-11 | sea_waves | CC-BY-3.0 |
| 1-28135-B-11 | sea_waves | CC-BY-3.0 |
| 1-29532-A-16 | wind | CC0-1.0 |
| 1-29680-A-21 | sneezing | CC-BY-3.0 |
| 1-30039-A-26 | laughing | CC-BY-3.0 |
| 1-30709-A-23 | breathing | CC0-1.0 |
| 1-31482-A-42 | siren | CC-BY-3.0 |
| 1-31482-B-42 | siren | CC-BY-3.0 |
| 1-32579-A-29 | drinking_sipping | CC-BY-NC-3.0 |
| 1-34094-A-5 | cat | CC-BY-3.0 |
| 1-34094-B-5 | cat | CC-BY-3.0 |
| 1-34495-A-14 | chirping_birds | CC-BY-NC-3.0 |
| 1-39835-A-9 | crow | CC-BY-3.0 |
| 1-41615-A-34 | can_opening | CC-BY-3.0 |
| 1-50625-A-17 | pouring_water | CC0-1.0 |
| 1-51805-A-33 | door_wood_creaks | CC0-1.0 |
| 1-51805-B-33 | door_wood_creaks | CC0-1.0 |
| 1-53501-A-32 | keyboard_typing | CC-BY-NC-3.0 |
| 1-54065-A-45 | train | CC-BY-3.0 |
| 1-57316-A-13 | crickets | CC-BY-3.0 |
| 1-57318-A-13 | crickets | CC-BY-3.0 |
| 1-84536-A-39 | glass_breaking | CC-BY-3.0 |

## Synthetic speech

`{synthetic: "Any English text.", voice: amy}`: a Piper TTS voice (`amy` or `lessac`).

