# Postcode grids

`<CC>_postcodes.json` holds the search cells of a country: `{"cells": [{"code", "town", "region",
"country_part", "lat", "lng"}]}`. One Google Maps search runs per cell.

| File | Cell | Cells | `region` is | `country_part` is |
|---|---|---|---|---|
| GB | outcode (`LS1`) | 3,002 | county | England / Scotland / Wales / NI |
| US | ZIP | 40,995 | state | state |
| CA | outcode (`M5V`) | 1,651 | province | province |
| AU | postcode | 3,171 | state | state |
| IE | Eircode routing key | 139 | province | province |
| DE | postcode (PLZ) | 8,173 | state (Bundesland) | state |

`<CC>.json` holds the language Google results are requested in (`DE` is `de`, so categories come back
German; all others `en`).

Any other country: `python3 pipeline/scrape/build_grid.py <CC>` writes both files from GeoNames
(one cell per postcode or per part before the space, bulk-mail codes like CEDEX dropped). Its
`<CC>.json` also carries a bounding box for the country filter and the postcode shape for reading
addresses, which the six shipped countries have in `pipeline/geo.py` and `pipeline/import_leads.py`.

Source: GeoNames postal code data, https://download.geonames.org/export/zip/ (CC BY 4.0).
