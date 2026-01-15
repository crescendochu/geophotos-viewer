// ========================================
// Tokyo 360° Street View - Viewer Page
// ========================================

// Mapbox access token - replace with your own
mapboxgl.accessToken = 'pk.eyJ1IjoiY3Jlc2NlbmRvY2h1IiwiYSI6ImNpdGR5MWZ5aDAycjIyc3A5ZHoxZzRwMGsifQ.nEaSxm520v7TpKAy2GG_kA';

// State
let neighborhood = null;
let photos = [];
let folders = {}; // Map folder name to folder data (including gpx_file)
let currentIndex = 0;
let viewer = null;
let map = null;
let activeMarker = null;
let photoColors = {}; // Map photo index to route color
let lineVisible = true;

// DOM Elements
const elements = {
  loading: document.getElementById('loading'),
  neighborhoodName: document.getElementById('neighborhood-name'),
  neighborhoodNameJa: document.getElementById('neighborhood-name-ja'),
  photoInfo: document.getElementById('photo-info'),
  panorama: document.getElementById('panorama'),
  minimap: document.getElementById('minimap'),
  minimapContainer: document.getElementById('minimap-container'),
  minimapToggle: document.getElementById('minimap-toggle'),
  lineToggle: document.getElementById('line-toggle'),
  prevBtn: document.getElementById('prev-btn'),
  nextBtn: document.getElementById('next-btn'),
  currentIndex: document.getElementById('current-index'),
  totalCount: document.getElementById('total-count'),
  // Debug elements
  debugFolder: document.getElementById('debug-folder'),
  debugFile: document.getElementById('debug-file'),
  debugCoords: document.getElementById('debug-coords'),
  debugGpx: document.getElementById('debug-gpx'),
  debugColor: document.getElementById('debug-color')
};

// ========================================
// Initialize
// ========================================
async function init() {
  try {
    // Get neighborhood ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const neighborhoodId = urlParams.get('neighborhood');
    
    if (!neighborhoodId) {
      window.location.href = 'index.html';
      return;
    }
    
    // Load data
    const [neighborhoodsData, indexData] = await Promise.all([
      fetch('../data/neighborhoods.json').then(r => r.json()),
      fetch(`../data/index.json?t=${Date.now()}`).then(r => r.json())
    ]);
    
    // Find neighborhood
    neighborhood = neighborhoodsData.neighborhoods.find(n => n.id === neighborhoodId);
    
    if (!neighborhood) {
      window.location.href = 'index.html';
      return;
    }
    
    // Store folders data for GPX file lookup
    if (indexData.folders) {
      indexData.folders.forEach(f => {
        folders[f.name] = f;
      });
    }
    
    // Get photos for this neighborhood
    photos = getPhotosForNeighborhood(neighborhood, indexData.photos);
    
    if (photos.length === 0) {
      console.error('No photos found for neighborhood');
      return;
    }
    
    // Update UI
    document.title = `${neighborhood.name} - Tokyo Walks`;
    elements.neighborhoodName.textContent = neighborhood.name;
    elements.neighborhoodNameJa.textContent = neighborhood.nameJa;
    elements.totalCount.textContent = photos.length;
    
    // Initialize viewer and map
    initPanorama();
    initMinimap();
    initControls();
    
    // Load first photo
    loadPhoto(0);
    
  } catch (error) {
    console.error('Failed to initialize viewer:', error);
  }
}

// ========================================
// Get Photos for Neighborhood
// ========================================
function getPhotosForNeighborhood(neighborhood, allPhotos) {
  return allPhotos.filter(photo => {
    if (photo.date !== neighborhood.date) return false;
    if (!photo.lat || !photo.lon) return false;
    
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
// Initialize Pannellum Panorama Viewer
// ========================================
function initPanorama() {
  viewer = pannellum.viewer('panorama', {
    type: 'equirectangular',
    panorama: '',
    autoLoad: false,
    showControls: false,
    mouseZoom: true,
    keyboardZoom: true,
    hfov: 100,
    minHfov: 50,
    maxHfov: 120,
    compass: false,
    northOffset: 0,
    showFullscreenCtrl: false,
    showZoomCtrl: false,
    friction: 0.15,
    yaw: 0,
    pitch: 0
  });
}

// ========================================
// Initialize Mapbox Minimap
// ========================================
function initMinimap() {
  map = new mapboxgl.Map({
    container: 'minimap',
    style: 'mapbox://styles/mapbox/dark-v11',
    center: [neighborhood.center[1], neighborhood.center[0]],
    zoom: 16,
    attributionControl: false
  });
  
  map.on('load', () => {
    // Group photos by folder (each folder = one route/direction)
    const routesByFolder = {};
    
    photos.forEach((photo, index) => {
      if (photo.lat && photo.lon && photo.folder) {
        if (!routesByFolder[photo.folder]) {
          routesByFolder[photo.folder] = [];
        }
        routesByFolder[photo.folder].push({ photo, index });
      }
    });
    
    // Generate distinct colors for each route
    const folderNames = Object.keys(routesByFolder);
    const routeColors = generateRouteColors(folderNames.length);
    
    // Track coordinate usage to offset overlapping points
    const coordCounts = {};
    
    // Build features for each route
    const allFeatures = [];
    
    folderNames.forEach((folder, routeIndex) => {
      const routePhotos = routesByFolder[folder];
      const color = routeColors[routeIndex];
      
      // Sort by timestamp within folder
      routePhotos.sort((a, b) => new Date(a.photo.timestamp) - new Date(b.photo.timestamp));
      
      // Create line for this route (using original coordinates)
      const lineCoords = routePhotos.map(r => [r.photo.lon, r.photo.lat]);
      if (lineCoords.length > 1) {
        allFeatures.push({
          type: 'Feature',
          properties: { color: color, routeIndex: routeIndex },
          geometry: {
            type: 'LineString',
            coordinates: lineCoords
          }
        });
      }
      
      // Create points for this route with offset for overlapping coords
      routePhotos.forEach(r => {
        const key = `${r.photo.lat.toFixed(6)},${r.photo.lon.toFixed(6)}`;
        if (!coordCounts[key]) {
          coordCounts[key] = 0;
        }
        const count = coordCounts[key];
        coordCounts[key]++;
        
        // Store color for this photo (for debug display)
        photoColors[r.index] = color;
        
        // Apply spiral offset for overlapping points
        const offset = getPointOffset(count);
        
        allFeatures.push({
          type: 'Feature',
          properties: { 
            index: r.index, 
            color: color,
            routeIndex: routeIndex
          },
          geometry: {
            type: 'Point',
            coordinates: [r.photo.lon + offset.lon, r.photo.lat + offset.lat]
          }
        });
      });
    });
    
    map.addSource('photos', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: allFeatures
      }
    });
    
    // Path layer (drawn first, underneath dots)
    map.addLayer({
      id: 'photos-path',
      type: 'line',
      source: 'photos',
      filter: ['==', '$type', 'LineString'],
      layout: {
        'line-join': 'round',
        'line-cap': 'round'
      },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 2.5,
        'line-opacity': 0.8
      }
    });
    
    updateLineVisibility();
    
    // Glow layer for all points
    map.addLayer({
      id: 'photos-glow',
      type: 'circle',
      source: 'photos',
      filter: ['==', '$type', 'Point'],
      paint: {
        'circle-radius': 6,
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.3,
        'circle-blur': 1
      }
    });
    
    // All photo points (on top)
    map.addLayer({
      id: 'photos-points',
      type: 'circle',
      source: 'photos',
      filter: ['==', '$type', 'Point'],
      paint: {
        'circle-radius': 3.5,
        'circle-color': ['get', 'color'],
        'circle-opacity': 1,
        'circle-stroke-width': 1,
        'circle-stroke-color': 'rgba(255, 255, 255, 0.6)'
      }
    });
    
    // Click handler for points
    map.on('click', 'photos-points', (e) => {
      if (e.features && e.features.length > 0) {
        const index = e.features[0].properties.index;
        loadPhoto(index);
      }
    });
    
    // Change cursor on hover
    map.on('mouseenter', 'photos-points', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    
    map.on('mouseleave', 'photos-points', () => {
      map.getCanvas().style.cursor = '';
    });
    
    // Add active marker (will be updated when photo changes)
    addActiveMarker();
    
    // Fit bounds
    const coordinates = photos.map(p => [p.lon, p.lat]);
    if (coordinates.length > 0) {
      const bounds = coordinates.reduce((bounds, coord) => {
        return bounds.extend(coord);
      }, new mapboxgl.LngLatBounds(coordinates[0], coordinates[0]));
      
      map.fitBounds(bounds, {
        padding: 40,
        duration: 0
      });
    }
  });
}

// ========================================
// Add Active Marker to Minimap
// ========================================
function addActiveMarker() {
  const el = document.createElement('div');
  el.className = 'active-marker';
  
  activeMarker = new mapboxgl.Marker({
    element: el,
    anchor: 'center'
  })
    .setLngLat([photos[0].lon, photos[0].lat])
    .addTo(map);
}

// ========================================
// Load Photo
// ========================================
function loadPhoto(index) {
  if (index < 0 || index >= photos.length) return;
  
  const photo = photos[index];
  currentIndex = index;
  
  // Show loading
  elements.loading.classList.remove('hidden');
  
  // Update panorama
  viewer.loadScene('default', undefined, undefined, undefined, () => {
    // Panorama loaded
    elements.loading.classList.add('hidden');
  });
  
  // Set new panorama
  const imagePath = `../photos/output/${photo.path}`;
  
  viewer.destroy();
  viewer = pannellum.viewer('panorama', {
    type: 'equirectangular',
    panorama: imagePath,
    autoLoad: true,
    showControls: false,
    mouseZoom: true,
    keyboardZoom: true,
    hfov: 100,
    minHfov: 50,
    maxHfov: 120,
    compass: false,
    showFullscreenCtrl: false,
    showZoomCtrl: false,
    friction: 0.15,
    yaw: 0,
    pitch: 0
  });
  
  viewer.on('load', () => {
    elements.loading.classList.add('hidden');
  });
  
  // Update UI
  elements.currentIndex.textContent = index + 1;
  elements.photoInfo.textContent = formatTimestamp(photo.timestamp);
  
  // Update button states
  elements.prevBtn.disabled = index === 0;
  elements.nextBtn.disabled = index === photos.length - 1;
  
  // Update debug info
  if (elements.debugFolder) {
    elements.debugFolder.textContent = photo.folder || 'N/A';
    elements.debugFile.textContent = photo.filename || 'N/A';
    elements.debugCoords.textContent = photo.lat && photo.lon 
      ? `${photo.lat.toFixed(6)}, ${photo.lon.toFixed(6)}` 
      : 'No coordinates';
    
    // Get GPX file from folder data
    const folderData = folders[photo.folder];
    elements.debugGpx.textContent = folderData?.gpx_file || 'No GPX';
    
    const color = photoColors[index] || '#999';
    elements.debugColor.innerHTML = `<span class="debug-color-swatch" style="background:${color}"></span>${color}`;
  }
  
  // Update map
  updateMapPosition(photo);
  
  // Update active marker
  updateActiveMarker(index);
}

// ========================================
// Update Map Position
// ========================================
function updateMapPosition(photo) {
  if (!map) return;
  
  map.flyTo({
    center: [photo.lon, photo.lat],
    zoom: 17,
    duration: 500
  });
}

// ========================================
// Update Active Marker
// ========================================
function updateActiveMarker(index) {
  if (activeMarker && photos[index]) {
    activeMarker.setLngLat([photos[index].lon, photos[index].lat]);
  }
}

// ========================================
// Toggle Route Lines
// ========================================
function updateLineVisibility() {
  if (!map || !map.getLayer('photos-path')) return;
  map.setLayoutProperty('photos-path', 'visibility', lineVisible ? 'visible' : 'none');
  
  if (elements.lineToggle) {
    elements.lineToggle.classList.toggle('is-off', !lineVisible);
    elements.lineToggle.title = lineVisible ? 'Hide route lines' : 'Show route lines';
    elements.lineToggle.setAttribute('aria-pressed', String(lineVisible));
  }
}

// ========================================
// Initialize Controls
// ========================================
function initControls() {
  // Previous/Next buttons
  elements.prevBtn.addEventListener('click', () => {
    loadPhoto(currentIndex - 1);
  });
  
  elements.nextBtn.addEventListener('click', () => {
    loadPhoto(currentIndex + 1);
  });
  
  // Keyboard navigation
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'a') {
      loadPhoto(currentIndex - 1);
    } else if (e.key === 'ArrowRight' || e.key === 'd') {
      loadPhoto(currentIndex + 1);
    }
  });
  
  // Minimap toggle - split screen mode
  elements.minimapToggle.addEventListener('click', () => {
    const container = document.querySelector('.viewer-container');
    container.classList.toggle('split-screen');
    
    // Resize both map and panorama after transition
    setTimeout(() => {
      map.resize();
      if (viewer) {
        viewer.resize();
      }
    }, 300);
  });
  
  // Line toggle - show/hide route lines
  if (elements.lineToggle) {
    elements.lineToggle.addEventListener('click', () => {
      lineVisible = !lineVisible;
      updateLineVisibility();
    });
  }
}

// ========================================
// Utilities
// ========================================
function formatTimestamp(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
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
