import { useEffect, useRef, useState } from 'react'
import { Autocomplete, Link, Stack, TextField, Typography } from '@mui/material'
import { searchAddresses } from '../../api'
import type { GeocodingSuggestion } from '../../api'

type LocationFieldsProps = {
  title?: string
  address: string
  latitude: string
  longitude: string
  onAddressChange: (address: string) => void
  onLatitudeChange: (latitude: string) => void
  onLongitudeChange: (longitude: string) => void
}

export function LocationFields({
  title,
  address,
  latitude,
  longitude,
  onAddressChange,
  onLatitudeChange,
  onLongitudeChange,
}: LocationFieldsProps) {
  const [suggestions, setSuggestions] = useState<GeocodingSuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedAddressRef = useRef<string | null>(null)

  useEffect(() => {
    const query = address.trim()
    if (query.length < 3) {
      selectedAddressRef.current = null
      setSuggestions([])
      setLoading(false)
      setError(null)
      return
    }
    if (query === selectedAddressRef.current) {
      setSuggestions([])
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()
    const timeout = window.setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        setSuggestions(await searchAddresses(query, controller.signal))
      } catch (caught) {
        if (!controller.signal.aborted) {
          setSuggestions([])
          setError(caught instanceof Error ? caught.message : 'Unable to search addresses.')
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, 300)

    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [address])

  return (
    <Stack spacing={1}>
      {title && <Typography variant="subtitle2">{title}</Typography>}
      <Autocomplete
        freeSolo
        filterOptions={(options) => options}
        getOptionLabel={(option) => typeof option === 'string' ? option : option.label}
        inputValue={address}
        loading={loading}
        noOptionsText={address.trim().length < 3 ? 'Type at least 3 characters' : 'No address found'}
        options={suggestions}
        onInputChange={(_, value, reason) => {
          onAddressChange(value)
          if (reason === 'input') {
            selectedAddressRef.current = null
            onLatitudeChange('')
            onLongitudeChange('')
          }
        }}
        onChange={(_, option) => {
          if (!option || typeof option === 'string') return
          selectedAddressRef.current = option.label
          onAddressChange(option.label)
          onLatitudeChange(option.latitude.toFixed(6))
          onLongitudeChange(option.longitude.toFixed(6))
          setSuggestions([])
        }}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Address"
            size="small"
            error={error !== null}
            helperText={error}
          />
        )}
      />
      <Stack direction="row" spacing={1}>
        <TextField
          label="Latitude"
          value={latitude}
          onChange={(event) => onLatitudeChange(event.target.value)}
          size="small"
          fullWidth
        />
        <TextField
          label="Longitude"
          value={longitude}
          onChange={(event) => onLongitudeChange(event.target.value)}
          size="small"
          fullWidth
        />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Address search by{' '}
        <Link href="https://photon.komoot.io" target="_blank" rel="noreferrer">
          Photon
        </Link>
        {' · '}©{' '}
        <Link
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          OpenStreetMap contributors
        </Link>
      </Typography>
    </Stack>
  )
}
