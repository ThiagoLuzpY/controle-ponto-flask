// flask_gps_ponto/static/script.js

window.onload = function () {
    const latitudeInput = document.getElementById("latitude");
    const longitudeInput = document.getElementById("longitude");
    const coordenadasDiv = document.getElementById("coordenadas");

    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
            function (position) {
                const lat = position.coords.latitude.toFixed(6);
                const lon = position.coords.longitude.toFixed(6);

                latitudeInput.value = lat;
                longitudeInput.value = lon;

                coordenadasDiv.innerHTML = `
                    📌 <strong>Localização detectada:</strong><br>
                    Latitude: <code>${lat}</code><br>
                    Longitude: <code>${lon}</code>
                `;
            },
            function (error) {
                coordenadasDiv.innerHTML = "❌ Não foi possível obter sua localização.";
                console.error("Erro ao obter localização:", error);
            }
        );
    } else {
        coordenadasDiv.innerHTML = "⚠️ Geolocalização não suportada neste navegador.";
    }
};
