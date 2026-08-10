// Create standard and satellite base layers.
const osmStandard = L.tileLayer(
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  {
    maxZoom: 16,
    attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors<br>',
  },
);
const usgsSatellite = L.tileLayer(
  "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}",
  {
    maxZoom: 16,
    attribution: 'Tiles courtesy of the <a href="https://usgs.gov/">U.S. Geological Survey</a>',
  },
);

// Create Leaflet map.
const map = L.map("map", {
  center: [39.833, -98.583],
  zoom: 4,
  layers: [osmStandard],
});

const baseMaps = {
  "OSM Standard": osmStandard,
  "USGS Satellite": usgsSatellite,
};
L.control.layers(baseMaps).addTo(map);
const markers = L.markerClusterGroup();

const companies = JSON.parse(document.getElementById("company_data").textContent);
const filterData = JSON.parse(document.getElementById("filter_data").textContent);

function generateFilters() {
  const filtersDiv = document.getElementById("filters");

  filterData.forEach((filter, index) => {
    const category = document.createElement("h5");
    category.textContent = filter.name;
    if (index !== 0) category.style.marginTop = "12px";
    filtersDiv.appendChild(category);

    filter.options.forEach((option) => {
      const div = document.createElement("div");
      div.className = "form-check";

      const input = document.createElement("input");
      input.type = filter.name === "Industry" ? "radio" : "checkbox";
      input.value = option.id;
      input.name = filter.name;
      input.id = `${filter.name}_${option.id}`;
      input.className = "form-check-input";

      const label = document.createElement("label");
      label.htmlFor = input.id;
      label.textContent = option.name;
      label.className = "form-check-label";

      div.appendChild(input);
      div.appendChild(label);
      filtersDiv.appendChild(div);
    });
  });
}

function getSelectedFilters() {
  const selected = {};

  filterData.forEach((filter) => {
    if (filter.name === "Industry") {
      const industryRadio = document.querySelector(
        `input[name="${filter.name}"]:checked`,
      );
      selected[filter.name] = industryRadio
        ? [parseInt(industryRadio.value, 10)]
        : [];
    } else {
      selected[filter.name] = Array.from(
        document.querySelectorAll(`input[name="${filter.name}"]:checked`),
      ).map((checkbox) => parseInt(checkbox.value, 10));
    }
  });
  return selected;
}

function updateCompanyCount(count) {
  const companyCount = document.getElementById("companyCount");
  companyCount.textContent = `${count} Active Companies Shown`;
}

function addMarkers() {
  markers.clearLayers();
  const selectedFilters = getSelectedFilters();
  let numMarkers = 0;

  companies.forEach((company) => {
    let shouldDisplay = true;

    for (const [category, selectedIds] of Object.entries(selectedFilters)) {
      if (selectedIds.length === 0) continue;

      const companyIds = company[category];
      if (category === "Industry") {
        if (!companyIds || !selectedIds.includes(companyIds)) {
          shouldDisplay = false;
          break;
        }
      } else {
        const companyIdsClean = companyIds || [];
        if (!selectedIds.every((id) => companyIdsClean.includes(id))) {
          shouldDisplay = false;
          break;
        }
      }
    }

    if (shouldDisplay) {
      const marker = L.marker([company.Latitude, company.Longitude], {
        title: company.Name,
      });

      let popupContent = `<b><a href="/companies/${company.id}" target="_blank">${company.Name}</a></b><br>`;
      popupContent += `Location: ${company.Location}<br>`;
      if (company.Phone) popupContent += `Phone: ${company.Phone}<br>`;
      if (company.Website) {
        popupContent += `Website: <a href="${company.Website}" target="_blank">${company.Website}</a>`;
      }

      marker.bindPopup(popupContent);
      markers.addLayer(marker);
      numMarkers += 1;
    }
  });

  map.addLayer(markers);
  updateCompanyCount(numMarkers);
}

function resetFilters() {
  document
    .querySelectorAll('input[type="checkbox"], input[type="radio"]')
    .forEach((input) => {
      input.checked = false;
    });
  addMarkers();
}

const customText = L.control({ position: "bottomleft" });
customText.onAdd = () => {
  const paragraph = L.DomUtil.create("p");
  paragraph.innerHTML = "Marker locations may be inaccurate.<br>Click markers for up to date locations.";
  return paragraph;
};
customText.addTo(map);

document.getElementById("applyButton").addEventListener("click", addMarkers);
document.getElementById("resetButton").addEventListener("click", resetFilters);
generateFilters();
addMarkers();
