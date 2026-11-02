# Company Map
This page explains the map implementation and its dependencies. See the [user documentation](USER.md#map) for instructions on using the map.

The company map used to be a static ArcGIS map embedded within the HempDB page. The current map shows companies with both latitude and longitude stored in the database, excluding companies with status ID `2` (inactive).

For historical background on the dynamic map and its filters, see PRs [#171](https://github.com/osu-cass/hemp-db/pull/171) and [#179](https://github.com/osu-cass/hemp-db/pull/179).

## Libraries and APIs
The map and markers are displayed using [LeafletJS](https://leafletjs.com/), and nearby markers are clustered using [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster).

Latitudes and longitudes (and other information) of each company are gathered in the `map()` view and sent to the `map.html` template using the [`json_script` template tag](https://docs.djangoproject.com/en/5.1/ref/templates/builtins/#json-script). From there, rendering is done on the frontend using JavaScript by parsing the company data in the `<script>` tag.

When geocoding runs, the [Geocoder](https://github.com/DenisCarriere/geocoder) Python library wraps the [ArcGIS Geocoding API](https://developers.arcgis.com/rest/geocode/). See `geocode_location()` in [`helloworld/views.py`](../helloworld/views.py) for the current implementation.

## Latitude and Longitude
Coordinates are stored in the database so map visits do not require external geocoding requests. Geocoding uses the available address, city, state, and country fields.

### When geocoding runs
The company create and edit forms use the following rules. Spreadsheet uploads do not run this geocoding helper.

**Creating a company**

1. The application attempts geocoding only when both coordinate values are falsy. The current check treats both empty values and zero as falsy.
2. If either coordinate is nonzero, geocoding is skipped and the submitted values are retained, even if the other coordinate is empty.

**Editing a company**

1. Changing Address, City, State, or Country triggers geocoding only if neither coordinate value changes.
2. Changing either coordinate value suppresses geocoding, even if location fields also change. Leaving all location and coordinate values unchanged does not trigger geocoding.

If geocoding fails or no usable location fields are supplied, the helper returns empty coordinates. These form submissions create pending company changes; approval is required before they affect the map, and companies without both coordinates are omitted.


## Map Caching
The `map()` view caches processed company data and filter options for 20 minutes using Django's Redis cache backend. The Compose stacks provide Valkey as the cache service, configured through `REDIS_URL`.

Save and delete signals in `helloworld/signals.py` invalidate both map cache keys for Company, Industry, Category, stakeholderGroups, Stage, and ProductGroup. Pending company proposals do not invalidate the cache until approval changes Company records. These handlers do not listen for changes made only to many-to-many relationships.

If a cache read fails, the view queries the database; if a cache write fails, it still renders the queried data. See `map()` in [`helloworld/views.py`](../helloworld/views.py) and [Django's caching documentation](https://docs.djangoproject.com/en/5.2/topics/cache/).
