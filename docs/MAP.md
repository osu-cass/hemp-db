# Company Map
This page explains the map implementation and its dependencies. See the [user documentation](USER.md#map) for instructions on using the map.

The company map used to be a static ArcGIS map embedded within the HempDB page. The current map shows active companies from the `company` table using their latitude and longitude fields.

The map in its current state was implemented in these PRs if you'd like to see the code: [#171](https://github.com/osu-cass/hemp-db/pull/171), [#179](https://github.com/osu-cass/hemp-db/pull/179).

## Libraries and APIs
The map and markers are displayed using [LeafletJS](https://leafletjs.com/), and the heatmap functionality uses [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster).

Latitudes and longitudes (and other information) of each company are gathered in the `map()` view and sent to the `map.html` template using the [`json_script` template tag](https://docs.djangoproject.com/en/5.1/ref/templates/builtins/#json-script). From there, rendering is done on the frontend using JavaScript by parsing the company data in the `<script>` tag.

To obtain the latitude and longitude of each company, we use the [Geocoder](https://github.com/DenisCarriere/geocoder) Python library. This acts as a wrapper around the [ArcGIS Geocoding API](https://developers.arcgis.com/rest/geocode/). See the [`geocode_location()` helper function](https://github.com/osu-cass/hemp-db/blob/2a06a99f6197d446936034fff9cee24b88b8b093/helloworld/views.py#L1468) in `views.py` to see how this is done in detail.

## Latitude and Longitude
Since we can't query all 5,000+ company latitudes and longitudes each time someone visits the map, we store them in the database. Previously, each company had a required country and an optional address. We now obtain the company's latitude and longitude from these available attributes.

### When geocoding runs
__Creating a company__
1. Without a latitude or longitude, the application attempts to geocode the provided location fields.
2. Providing a lat/lng will not trigger the geocode and will use entered value(s)

__Editing a company__
1. Changing any of the location fields (Address, City, State, or Country), will automatically trigger a new query and update the company's lat/lng accordingly
2. However, you can manually edit the lat/lng as well and no geocode query will override this edit

Latitude and longitude values entered by a user take precedence. Otherwise, HempDB calls the geocoding API to obtain the coordinates.


## Map Caching
You may notice when visiting the map page for the first time in awhile, it takes ~5 seconds to load, but subsequent refreshes of the page are faster. This is because we cache the queried company data from the database.

Signals in `signals.py` are used to invalidate the cached data when the applicable models are created, edited, or deleted so the map isn't showing dated information.

The cache stores data in memory for better performance. More details about this can be seen in the `map()` view, and Django's caching documentation can be found [here](https://docs.djangoproject.com/en/5.2/topics/cache/).
