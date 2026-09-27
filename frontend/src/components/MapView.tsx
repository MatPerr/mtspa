import { useEffect, useRef } from 'react'
import L from 'leaflet'
import type { AgentDraft, AppointmentDraft, Coordinate, TourResult } from '../types'

const TOUR_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#ca8a04', '#db2777']
const MUTED_TOUR_COLOR = '#9ca3af'

function createAgentHomeIcon(color: string) {
  return L.divIcon({
    className: 'agent-home-icon',
    html: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 1.5 22.5 22.5H1.5Z" fill="${color}" stroke="#ffffff" stroke-width="2" />
      </svg>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12],
  })
}

type MapViewProps = {
  agents: AgentDraft[]
  appointments: AppointmentDraft[]
  tours: TourResult[]
  selectedAgentId: number | null
  onMapClick: (coordinate: Coordinate) => void
}

export function MapView({
  agents,
  appointments,
  tours,
  selectedAgentId,
  onMapClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const contentLayerRef = useRef<L.LayerGroup | null>(null)
  const clickHandlerRef = useRef(onMapClick)
  clickHandlerRef.current = onMapClick

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current).setView([50.85, 4.55], 8)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)
    const contentLayer = L.layerGroup().addTo(map)
    map.on('click', (event: L.LeafletMouseEvent) => {
      clickHandlerRef.current({
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
      })
    })
    mapRef.current = map
    contentLayerRef.current = contentLayer
    window.setTimeout(() => map.invalidateSize(), 0)

    return () => {
      map.remove()
      mapRef.current = null
      contentLayerRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = contentLayerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    const visibleCoordinates: L.LatLngExpression[] = []
    const appointmentColors = new Map<number, string>()
    const tourColor = (agentId: number) => (
      selectedAgentId !== null && agentId !== selectedAgentId
        ? MUTED_TOUR_COLOR
        : TOUR_COLORS[agentId % TOUR_COLORS.length]
    )

    tours.forEach((tour) => {
      const color = tourColor(tour.agent_id)
      tour.appointment_ids.forEach((appointmentId) => {
        appointmentColors.set(appointmentId, color)
      })
    })

    const orderedTours = selectedAgentId === null
      ? tours
      : [
          ...tours.filter((tour) => tour.agent_id !== selectedAgentId),
          ...tours.filter((tour) => tour.agent_id === selectedAgentId),
        ]
    orderedTours.forEach((tour) => {
      const coordinates = tour.coordinates.map(
        ({ latitude, longitude }) => [latitude, longitude] as L.LatLngExpression,
      )
      L.polyline(coordinates, {
        color: tourColor(tour.agent_id),
        weight: tour.agent_id === selectedAgentId ? 5 : 4,
        opacity: selectedAgentId !== null && tour.agent_id !== selectedAgentId ? 0.45 : 0.78,
      }).addTo(layer)
    })

    agents.forEach((agent, index) => {
      const coordinate: L.LatLngExpression = [agent.latitude, agent.longitude]
      visibleCoordinates.push(coordinate)
      L.marker(coordinate, {
        icon: createAgentHomeIcon(tourColor(index)),
      })
        .bindTooltip(`Agent ${index + 1}: ${agent.name}`)
        .addTo(layer)
    })

    appointments.forEach((appointment, index) => {
      const coordinate: L.LatLngExpression = [appointment.latitude, appointment.longitude]
      const appointmentId = index + 1
      visibleCoordinates.push(coordinate)
      L.circleMarker(coordinate, {
        radius: 7,
        color: '#ffffff',
        weight: 2,
        fillColor: appointmentColors.get(appointmentId) ?? '#000000',
        fillOpacity: 0.95,
      })
        .bindTooltip(`Appointment ${appointmentId} · ${appointment.time}`)
        .addTo(layer)
    })

    const selectedTour = tours.find((tour) => tour.agent_id === selectedAgentId)
    if (selectedTour) {
      const selectedCoordinates = selectedTour.coordinates.map(
        ({ latitude, longitude }) => L.latLng(latitude, longitude),
      )
      const selectedBounds = L.latLngBounds(selectedCoordinates)
      if (selectedBounds.getNorthEast().equals(selectedBounds.getSouthWest())) {
        map.setView(selectedCoordinates[0], 13)
      } else {
        map.fitBounds(selectedBounds, { padding: [60, 60], maxZoom: 14 })
      }
    } else if (visibleCoordinates.length === 1) {
      map.setView(visibleCoordinates[0], 12)
    } else if (visibleCoordinates.length > 1) {
      map.fitBounds(L.latLngBounds(visibleCoordinates), { padding: [40, 40], maxZoom: 14 })
    }
  }, [agents, appointments, tours, selectedAgentId])

  return <div ref={containerRef} className="map" aria-label="Problem map" />
}
