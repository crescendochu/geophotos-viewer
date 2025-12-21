// ========================================
// Tokyo 360° Street View - Home Page
// ========================================

// Mapbox access token - replace with your own
mapboxgl.accessToken = 'pk.eyJ1IjoiY3Jlc2NlbmRvY2h1IiwiYSI6ImNpdGR5MWZ5aDAycjIyc3A5ZHoxZzRwMGsifQ.nEaSxm520v7TpKAy2GG_kA';

// State
let neighborhoods = [];
let photoIndex = {};
let maps = {};

// ========================================
// Initialize
// ========================================
async function init() {
  try {
    // Load data
    const [neighborhoodsData, indexData] = await Promise.all([
      fetch('data/neighborhoods.json').then(r => r.json()),
      fetch('data/index.json').then(r => r.json())
    ]);
    
    neighborhoods = neighborhoodsData.neighborhoods;
    photoIndex = indexData;
    
    // Process photos for each neighborhood
    neighborhoods.forEach(neighborhood => {
      neighborhood.photos = getPhotosForNeighborhood(neighborhood, indexData.photos);
    });
    
    // Render cards
    renderNeighborhoodCards();
    
  } catch (error) {
    console.error('Failed to initialize:', error);
  }
}

// ========================================
// Get Photos for Neighborhood
// ========================================
function getPhotosForNeighborhood(neighborhood, allPhotos) {
  return allPhotos.filter(photo => {
    // Must match the date
    if (photo.date !== neighborhood.date) return false;
    
    // Must have coordinates
    if (!photo.lat || !photo.lon) return false;
    
    // Check time range if specified
    if (neighborhood.timeRange) {
      const photoTime = new Date(photo.timestamp).getTime();
      const startTime = new Date(neighborhood.timeRange.start).getTime();
      const endTime = new Date(neighborhood.timeRange.end).getTime();
      if (photoTime < startTime || photoTime > endTime) return false;
    }
    
    return true;
  }).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
}

// ========================================
// Render Neighborhood Cards
// ========================================
function renderNeighborhoodCards() {
  const grid = document.getElementById('neighborhoods-grid');
  
  neighborhoods.forEach((neighborhood, index) => {
    const card = document.createElement('div');
    card.className = 'neighborhood-card';
    card.style.animationDelay = `${index * 100}ms`;
    
    card.innerHTML = `
      <div class="card-map" id="map-${neighborhood.id}"></div>
      <div class="card-overlay"></div>
      <div class="card-content">
        <div class="card-header">
          <h2 class="card-name">${neighborhood.name}</h2>
          <span class="card-name-ja">${neighborhood.nameJa}</span>
        </div>
        <p class="card-description">${neighborhood.description}</p>
        <div class="card-meta">
          <div class="card-meta-item">
            <svg class="card-meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
            <span>${formatDate(neighborhood.date)}</span>
          </div>
          <div class="card-meta-item">
            <svg class="card-meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <path d="M21 15l-5-5L5 21"/>
            </svg>
            <span>${neighborhood.photos.length} photos</span>
          </div>
        </div>
      </div>
      <div class="card-arrow">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </div>
    `;
    
    card.addEventListener('click', () => {
      window.location.href = `viewer.html?neighborhood=${neighborhood.id}`;
    });
    
    grid.appendChild(card);
    
    // Initialize map after card is in DOM
    setTimeout(() => initCardMap(neighborhood), 50);
  });
}

// ========================================
// Initialize Card Map
// ========================================
function initCardMap(neighborhood) {
  const mapContainer = document.getElementById(`map-${neighborhood.id}`);
  if (!mapContainer) return;
  
  const map = new mapboxgl.Map({
    container: mapContainer,
    style: 'mapbox://styles/mapbox/dark-v11',
    center: [neighborhood.center[1], neighborhood.center[0]],
    zoom: 15,
    interactive: false,
    attributionControl: false
  });
  
  maps[neighborhood.id] = map;
  
  map.on('load', () => {
    // Add route line
    if (neighborhood.photos.length > 1) {
      const coordinates = neighborhood.photos
        .filter(p => p.lat && p.lon)
        .map(p => [p.lon, p.lat]);
      
      map.addSource(`route-${neighborhood.id}`, {
        type: 'geojson',
        data: {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'LineString',
            coordinates: coordinates
          }
        }
      });
      
      map.addLayer({
        id: `route-line-${neighborhood.id}`,
        type: 'line',
        source: `route-${neighborhood.id}`,
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': '#e85d4c',
          'line-width': 3,
          'line-opacity': 0.8
        }
      });
      
      // Fit bounds to route
      if (coordinates.length > 0) {
        const bounds = coordinates.reduce((bounds, coord) => {
          return bounds.extend(coord);
        }, new mapboxgl.LngLatBounds(coordinates[0], coordinates[0]));
        
        map.fitBounds(bounds, {
          padding: 40,
          duration: 0
        });
      }
    }
  });
}

// ========================================
// Utilities
// ========================================
function formatDate(dateStr) {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { 
    month: 'short', 
    day: 'numeric',
    year: 'numeric'
  });
}

// ========================================
// Start
// ========================================
document.addEventListener('DOMContentLoaded', init);
