# 0031: AC and DC power key on the map

Date: 2026-10-30. Status: accepted.

The owner asked whether the map's key should separate AC from DC charging. Many cars take
7 or 11 kW at most on AC, whatever a 22 kW post offers, but can use far more on DC, so a
band that mixes the two says little about how fast a visitor can charge. This replaces
the point colours in ADR 0012; the rest of that ADR stands.

## What the data showed

From the live map file of 30 October 2026 (32,854 locations):

- The old four bands (under 8, 8 to 49, 50 to 149, 150 kW or more) are exactly the
  Department for Transport's power bands in its charging statistics, which do not split
  AC from DC.
- The 8 to 49 kW band was mostly AC: 4,870 of its 5,058 locations took their colour from
  an AC connector (mostly 22 kW) and 188 from DC (mostly 25 and 40 kW).
- The under 8 kW band held 73% of the map: about 20,500 locations under 6 kW, mostly lamp
  posts at 3 to 5 kW, and about 3,500 at 7 kW.
- In 1,253 detail files, the feed's power_type agreed with the plug on 3,755 of 3,761
  connectors where both were known (99.8%).

## Decisions

- **AC or DC comes from the feed's power_type only.** Each kind of connector in
  `locations.geojson` has `cur`: `ac` (any `AC_` value) or `dc`, and null when the feed
  gives no OCPI 2.2.1 value. It is never read from the plug, so a Type 2 socket a feed
  marks DC shows as DC, and a feed with no valid power_type shows as "not stated".
- **A location takes the band of its fastest DC connector, or of its fastest AC one
  where it has no DC.** Only 6 locations had an AC connector faster than their fastest
  DC one.
- **Seven bands.** AC: under 6 kW, 6 to 10 kW, 11 kW or more. DC: under 50, 50 to 99,
  100 to 149, 150 kW or more. The DC steps keep the rapid (50 kW) and ultra-rapid
  (150 kW) edges. 6 kW splits lamp posts from 7 kW posts, which feeds give as anything
  from 6.4 to 7.7 kW. Grey means the power, or AC or DC, is not stated.
- **Shape tells AC from DC: circles for AC, diamonds for DC.** The owner found shades of
  one colour hard to tell apart and asked about colour blindness, a rainbow, or shapes.
  Shape works for every visitor, so colour only has to separate the bands within a
  shape. The diamonds are drawn on a canvas, like the price label boxes (ADR 0026);
  where a browser cannot draw them, DC points stay circles.
- **Colours were chosen by measurement, not by eye.** AC: mint, blue, navy. DC: yellow,
  orange, magenta, purple. Within each shape every pair stays apart under simulated
  protanopia, deuteranopia and tritanopia (Machado 2009 model, OKLab difference of at
  least 8), and under normal vision (at least 15), with room to spare. No set of seven
  colours on one shape came close, which is why shape carries AC and DC. A rainbow was
  not used because red, orange and green merge for red-green colour blindness. Points
  still grow with power, and the letter on each is white or near black, whichever has
  at least 4.5:1 contrast.
- **The key shows the AC and DC symbols** (a sine wave and a line over dashes) beside
  its AC and DC headings.
- **Filters:** a new "AC or DC" choice (`?cur=ac` or `?cur=dc`), applied to the same
  connector as the other conditions, and power steps of 11, 100 and 300 kW beside the
  old 7, 22, 50 and 150. Old addresses still work.
- **Two changes, in order.** The data field went first (PR #109) and the map change
  after a daily run had published it, because a push to main redeploys with the last
  day's data and every point would otherwise show as "not stated" until the next fetch.

## Not done

- Drawing the AC or DC symbol inside each marker, which would replace the price letter.
  The owner chose shapes instead.
- A setting for the visitor's own car (for example "my car takes 11 kW on AC"), which
  would recolour AC posts by what the car can use.
