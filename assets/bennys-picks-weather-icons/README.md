# Benny's Picks weather icons

12 individual PNG icons with real transparent backgrounds, designed for the dark green weather table. Original images are 1254 × 1254 pixels. These are raster PNGs, not SVGs.

## Quick use

1. Copy the `png` directory into your website's assets directory.
2. Put a 40 × 40 pixel image box immediately before the temperature and condition text. The transparent margin makes the visible symbol about 28–32 pixels wide.
3. Keep a short condition label beside the icon.
4. Open `preview.html` locally to see the set and sample placement. No external resources are required.

```html
<span class="weather-condition">
  <img src="/assets/weather/png/partly-cloudy.png"
       width="40" height="40" alt="" aria-hidden="true">
  <span>72°F, partly cloudy · wind 4 mph</span>
</span>
```

```css
.weather-condition {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.weather-condition img {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  object-fit: contain;
}
```

Use an empty `alt` attribute when nearby text already states the condition. When an icon appears alone, give it meaningful alternative text, such as `alt="Partly cloudy"`.

## Files

| File | Meaning |
| --- | --- |
| `png/sunny.png` | Sunny |
| `png/partly-cloudy.png` | Partly cloudy |
| `png/cloudy.png` | Cloudy / overcast |
| `png/clear-night.png` | Clear night |
| `png/partly-cloudy-night.png` | Partly cloudy night |
| `png/rain.png` | Rain |
| `png/thunderstorm.png` | Thunderstorm |
| `png/snow.png` | Snow |
| `png/sleet.png` | Rain / snow mix |
| `png/fog.png` | Fog |
| `png/wind.png` | Wind |
| `png/indoor.png` | Indoors / closed roof |

## Display notes

- Choose the sun or moon variant according to daytime or nighttime at the stadium.
- Show wind as an additional indicator when useful; wind can coexist with sunshine or rain.
- Use the indoor icon for games played under a closed roof. A retractable roof by itself does not establish that it is closed.
- Preserve the temperature, wind speed, and any relevant gust value as text.

The original generated PNGs are included unchanged. `generation-prompts.json` contains the prompts used to create the set with the built-in image generation tool.
