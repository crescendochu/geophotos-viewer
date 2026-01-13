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
      fetch('../data/neighborhoods.json').then(r => r.json()),
      fetch(`../data/index.json?t=${Date.now()}`).then(r => r.json())
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
    if (neighborhood.photos.length > 0) {
      // Group photos by folder (each folder = one route/direction)
      const routesByFolder = {};
      
      neighborhood.photos.forEach(photo => {
        if (photo.lat && photo.lon && photo.folder) {
          if (!routesByFolder[photo.folder]) {
            routesByFolder[photo.folder] = [];
          }
          routesByFolder[photo.folder].push(photo);
        }
      });
      
      // Generate distinct colors for each route
      const folderNames = Object.keys(routesByFolder);
      const routeColors = generateRouteColors(folderNames.length);
      
      // Track coordinate usage to offset overlapping points
      const coordCounts = {};
      
      // Build features for each route
      const allFeatures = [];
      const allCoordinates = [];
      
      folderNames.forEach((folder, routeIndex) => {
        const routePhotos = routesByFolder[folder];
        const color = routeColors[routeIndex];
        
        // Sort by timestamp within folder
        routePhotos.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        
        // Create line for this route
        const lineCoords = routePhotos.map(p => [p.lon, p.lat]);
        allCoordinates.push(...lineCoords);
        
        if (lineCoords.length > 1) {
          allFeatures.push({
            type: 'Feature',
            properties: { color: color },
            geometry: {
              type: 'LineString',
              coordinates: lineCoords
            }
          });
        }
        
        // Create points for this route with offset for overlapping coords
        routePhotos.forEach(p => {
          const key = `${p.lat.toFixed(6)},${p.lon.toFixed(6)}`;
          if (!coordCounts[key]) {
            coordCounts[key] = 0;
          }
          const count = coordCounts[key];
          coordCounts[key]++;
          
          // Apply spiral offset for overlapping points
          const offset = getPointOffset(count);
          
          allFeatures.push({
            type: 'Feature',
            properties: { color: color },
            geometry: {
              type: 'Point',
              coordinates: [p.lon + offset.lon, p.lat + offset.lat]
            }
          });
        });
      });
      
      map.addSource(`route-${neighborhood.id}`, {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: allFeatures
        }
      });
      
      // Path layer
      map.addLayer({
        id: `route-${neighborhood.id}`,
        type: 'line',
        source: `route-${neighborhood.id}`,
        filter: ['==', '$type', 'LineString'],
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 2,
          'line-opacity': 0.7
        }
      });
      
      // Glow layer for points
      map.addLayer({
        id: `points-glow-${neighborhood.id}`,
        type: 'circle',
        source: `route-${neighborhood.id}`,
        filter: ['==', '$type', 'Point'],
        paint: {
          'circle-radius': 5,
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.3,
          'circle-blur': 1
        }
      });
      
      // Points layer
      map.addLayer({
        id: `points-${neighborhood.id}`,
        type: 'circle',
        source: `route-${neighborhood.id}`,
        filter: ['==', '$type', 'Point'],
        paint: {
          'circle-radius': 2.5,
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.9,
          'circle-stroke-width': 0.5,
          'circle-stroke-color': 'rgba(255, 255, 255, 0.5)'
        }
      });
      
      // Fit bounds to all points
      if (allCoordinates.length > 0) {
        const bounds = allCoordinates.reduce((bounds, coord) => {
          return bounds.extend(coord);
        }, new mapboxgl.LngLatBounds(allCoordinates[0], allCoordinates[0]));
        
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

// Calculate offset for overlapping points (spiral pattern)
function getPointOffset(index) {
  if (index === 0) {
    return { lat: 0, lon: 0 };
  }
  
  // Spiral offset - each subsequent point gets placed in a circle around the original
  const offsetDistance = 0.00003; // ~3 meters at Tokyo's latitude
  const angle = (index * 137.5) * (Math.PI / 180); // Golden angle for even distribution
  const radius = offsetDistance * Math.sqrt(index);
  
  return {
    lat: radius * Math.cos(angle),
    lon: radius * Math.sin(angle)
  };
}

// Generate visually distinct colors for routes
function generateRouteColors(count) {
  const baseColors = [
    '#22d3ee', // cyan
    '#f97316', // orange
    '#a855f7', // purple
    '#10b981', // emerald
    '#f43f5e', // rose
    '#3b82f6', // blue
    '#eab308', // yellow
    '#ec4899', // pink
    '#14b8a6', // teal
    '#8b5cf6', // violet
    '#84cc16', // lime
    '#06b6d4', // cyan-500
    '#f59e0b', // amber
    '#6366f1', // indigo
    '#ef4444', // red
    '#0ea5e9', // sky
    '#d946ef', // fuchsia
    '#22c55e', // green
  ];
  
  const colors = [];
  for (let i = 0; i < count; i++) {
    colors.push(baseColors[i % baseColors.length]);
  }
  return colors;
}

// ========================================
// Start
// ========================================
document.addEventListener('DOMContentLoaded', init);
