async function inicializar() {
  const urlConfig = document.body.dataset.api;
  const respuesta = await fetch(urlConfig);
  const config = await respuesta.json();

  const datos = config.datosPersonales;
  const ubicacion = config.ubicacion;

  document.getElementById("nombre").textContent = datos.nombre;
  document.getElementById("ocupacion").textContent = datos.ocupacion;
  document.title = datos.nombre + " · " + datos.ocupacion + " · America";

  const coordenadas = [ubicacion.lat, ubicacion.lng];

  const mapa = L.map("mapa-leaflet").setView(coordenadas, ubicacion.zoom || 15);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors",
  }).addTo(mapa);

  L.marker(coordenadas)
    .addTo(mapa)
    .bindPopup(ubicacion.etiqueta)
    .openPopup();
}

inicializar();
