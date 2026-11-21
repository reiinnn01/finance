(function () {
  var element = document.getElementById('map');
  if (!element || typeof L === 'undefined') return;
  var points = JSON.parse(document.getElementById('client-points').textContent);
  var map = L.map('map').setView([14.2117, 121.1653], 11);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    referrerPolicy: 'strict-origin-when-cross-origin',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var bounds = [];
  points.forEach(function (p) {
    var marker = L.marker([p.lat, p.lng]).addTo(map);
    var popup = document.createElement('div');
    var title = document.createElement('strong');
    title.textContent = p.name;
    var line = document.createElement('div');
    line.textContent = p.address;
    var link = document.createElement('a');
    link.href = p.url;
    link.textContent = 'Open profile';
    popup.appendChild(title);
    popup.appendChild(line);
    popup.appendChild(link);
    marker.bindPopup(popup);
    bounds.push([p.lat, p.lng]);
  });

  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
})();
