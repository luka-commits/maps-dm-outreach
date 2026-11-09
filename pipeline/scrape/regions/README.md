# Postcode grids

`<CC>_postcodes.json` holds the search cells of a country: `{"liste": [{"code", "ort", "region",
"land_region", "lat", "lng"}]}`. One Google Maps search runs per cell.

| File | Cell | Cells | `region` is | `land_region` is |
|---|---|---|---|---|
| GB | outcode (`LS1`) | 3,002 | county | England / Scotland / Wales / NI |
| US | ZIP | 40,995 | state | state |
| CA | outcode (`M5V`) | 1,651 | province | province |
| AU | postcode | 3,171 | state | state |
| IE | Eircode routing key | 139 | province | province |
| DE | PLZ | 8,173 | Bundesland | Bundesland |

`<CC>.json` holds the language Google results are requested in (`DE` is `de`, so categories come back
German; all others `en`).

Source: GeoNames postal code data, https://download.geonames.org/export/zip/ (CC BY 4.0).
