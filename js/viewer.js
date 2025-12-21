// ========================================
// Tokyo 360° Street View - Viewer Page
// ========================================

// Mapbox access token - replace with your own
mapboxgl.accessToken = 'pk.eyJ1IjoiY3Jlc2NlbmRvY2h1IiwiYSI6ImNpdGR5MWZ5aDAycjIyc3A5ZHoxZzRwMGsifQ.nEaSxm520v7TpKAy2GG_kA';

// State
let neighborhood = null;
let photos = [];
let currentIndex = 0;
let viewer = null;
let map = null;
let markers = [];
let activeMarker = null;

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
  prevBtn: document.getElementById('prev-btn'),
  nextBtn: document.getElementById('next-btn'),
  currentIndex: document.getElementById('current-index'),
  totalCount: document.getElementById('total-count')
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
      fetch('data/neighborhoods.json').then(r => r.json()),
      fetch('data/index.json').then(r => r.json())
    ]);
    
    // Find neighborhood
    neighborhood = neighborhoodsData.neighborhoods.find(n => n.id === neighborhoodId);
    
    if (!neighborhood) {
      window.location.href = 'index.html';
      return;
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
    // Add route line
    const coordinates = photos.map(p => [p.lon, p.lat]);
    
    map.addSource('route', {
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
    
    // Route line glow
    map.addLayer({
      id: 'route-glow',
      type: 'line',
      source: 'route',
      layout: {
        'line-join': 'round',
        'line-cap': 'round'
      },
      paint: {
        'line-color': '#e85d4c',
        'line-width': 8,
        'line-opacity': 0.3,
        'line-blur': 3
      }
    });
    
    // Route line
    map.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route',
      layout: {
        'line-join': 'round',
        'line-cap': 'round'
      },
      paint: {
        'line-color': '#e85d4c',
        'line-width': 3,
        'line-opacity': 0.9
      }
    });
    
    // Add photo markers
    addPhotoMarkers();
    
    // Fit bounds
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
// Add Photo Markers to Minimap
// ========================================
function addPhotoMarkers() {
  // Only add markers for every Nth photo to avoid clutter
  const step = Math.max(1, Math.floor(photos.length / 30));
  
  photos.forEach((photo, index) => {
    // Always add first, last, and every Nth marker
    if (index !== 0 && index !== photos.length - 1 && index % step !== 0) {
      return;
    }
    
    const el = document.createElement('div');
    el.className = 'route-marker';
    el.dataset.index = index;
    
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      loadPhoto(index);
    });
    
    const marker = new mapboxgl.Marker({
      element: el,
      anchor: 'center'
    })
      .setLngLat([photo.lon, photo.lat])
      .addTo(map);
    
    markers.push({ marker, element: el, index });
  });
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
  const imagePath = `photos/${photo.path}`;
  
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
  // Remove active class from all markers
  markers.forEach(m => {
    m.element.classList.remove('active');
  });
  
  // Find and activate the nearest marker
  let nearestMarker = null;
  let minDistance = Infinity;
  
  markers.forEach(m => {
    const distance = Math.abs(m.index - index);
    if (distance < minDistance) {
      minDistance = distance;
      nearestMarker = m;
    }
  });
  
  if (nearestMarker) {
    nearestMarker.element.classList.add('active');
    activeMarker = nearestMarker;
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
  
  // Minimap toggle
  elements.minimapToggle.addEventListener('click', () => {
    elements.minimapContainer.classList.toggle('expanded');
    map.resize();
  });
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

// ========================================
// Start
// ========================================
document.addEventListener('DOMContentLoaded', init);
