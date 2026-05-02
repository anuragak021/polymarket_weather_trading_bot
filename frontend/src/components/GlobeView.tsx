import { useEffect, useRef, useMemo, useCallback } from 'react'
import Globe from 'react-globe.gl'
import type { WeatherForecast, WeatherSignal } from '../types'

interface Props {
  forecasts: WeatherForecast[]
  signals: WeatherSignal[]
}

interface CityMarker {
  lat: number
  lng: number
  name: string
  key: string
  forecast: WeatherForecast | null
  bestSignal: WeatherSignal | null
  hasActionable: boolean
}

export function GlobeView({ forecasts, signals }: Props) {
  const globeRef = useRef<any>(null)

  const markers: CityMarker[] = useMemo(() => {
    return forecasts
      .filter(f => f.lat !== null && f.lat !== undefined && f.lon !== null && f.lon !== undefined)
      .map(forecast => {
        const citySignals = signals.filter(s => s.city_key === forecast.city_key)
        const actionableSignals = citySignals.filter(s => s.actionable)
        const bestSignal = actionableSignals.length > 0
          ? actionableSignals.reduce((a, b) => Math.abs(a.edge) > Math.abs(b.edge) ? a : b)
          : citySignals.length > 0
            ? citySignals.reduce((a, b) => Math.abs(a.edge) > Math.abs(b.edge) ? a : b)
            : null

        return {
          lat: forecast.lat as number,
          lng: forecast.lon as number,
          name: forecast.city_name,
          key: forecast.city_key,
          forecast,
          bestSignal,
          hasActionable: actionableSignals.length > 0,
        }
      })
  }, [forecasts, signals])

  useEffect(() => {
    if (globeRef.current) {
      globeRef.current.pointOfView({ lat: 20, lng: 0, altitude: 2.4 }, 1000)
      globeRef.current.controls().autoRotate = true
      globeRef.current.controls().autoRotateSpeed = 0.3
      globeRef.current.controls().enableZoom = false
    }
  }, [])

  const handleInteraction = useCallback(() => {
    if (globeRef.current) {
      globeRef.current.controls().autoRotate = false
      setTimeout(() => {
        if (globeRef.current) {
          globeRef.current.controls().autoRotate = true
        }
      }, 5000)
    }
  }, [])

  const markerElement = useCallback((d: object) => {
    const marker = d as CityMarker
    const el = document.createElement('div')
    el.className = 'city-marker'

    const dotColor = marker.hasActionable ? '#22c55e' : marker.bestSignal ? '#d97706' : '#525252'

    const dot = document.createElement('div')
    dot.className = 'marker-dot'
    dot.style.backgroundColor = dotColor
    dot.style.color = dotColor
    el.appendChild(dot)

    const label = document.createElement('div')
    label.className = 'marker-label'

    const nameSpan = document.createElement('div')
    nameSpan.className = 'marker-name'
    nameSpan.textContent = marker.name
    label.appendChild(nameSpan)

    if (marker.forecast) {
      const tempSpan = document.createElement('div')
      tempSpan.className = 'marker-temp'
      tempSpan.style.color = '#e5e5e5'
      tempSpan.textContent = `${marker.forecast.mean_high.toFixed(0)}F`
      label.appendChild(tempSpan)
    }

    if (marker.bestSignal) {
      const edgeSpan = document.createElement('div')
      edgeSpan.className = 'marker-edge'
      const edgeVal = (marker.bestSignal.edge * 100).toFixed(1)
      edgeSpan.style.color = marker.bestSignal.edge > 0 ? '#22c55e' : '#dc2626'
      edgeSpan.textContent = `${marker.bestSignal.edge > 0 ? '+' : ''}${edgeVal}%`
      label.appendChild(edgeSpan)
    }

    el.appendChild(label)
    return el
  }, [])

  return (
    <div className="globe-container w-full h-full">
      <Globe
        ref={globeRef}
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        backgroundColor="rgba(0,0,0,0)"
        atmosphereColor="#1a1a2e"
        atmosphereAltitude={0.15}
        htmlElementsData={markers}
        htmlElement={markerElement}
        htmlAltitude={0.01}
        onGlobeClick={handleInteraction}
        width={undefined}
        height={undefined}
      />
    </div>
  )
}
