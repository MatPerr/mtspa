import { useEffect, useState } from 'react'
import { Alert, Button, Stack, TextField } from '@mui/material'
import type { AppointmentDraft, Coordinate } from '../../types'
import { LocationFields } from './LocationFields'

type AppointmentFormProps = {
  pickedLocation: Coordinate | null
  onAdd: (appointment: Omit<AppointmentDraft, 'id'>) => void
}

export function AppointmentForm({ pickedLocation, onAdd }: AppointmentFormProps) {
  const [time, setTime] = useState('09:00')
  const [durationMinutes, setDurationMinutes] = useState(30)
  const [gain, setGain] = useState(100)
  const [address, setAddress] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!pickedLocation) return
    setAddress('')
    setLatitude(pickedLocation.latitude.toFixed(6))
    setLongitude(pickedLocation.longitude.toFixed(6))
  }, [pickedLocation])

  const submit = () => {
    const parsedLatitude = Number(latitude)
    const parsedLongitude = Number(longitude)
    if (latitude === '' || longitude === '') {
      setError('Coordinates are required. Find an address or click the map.')
      return
    }
    if (!Number.isFinite(parsedLatitude) || !Number.isFinite(parsedLongitude)) {
      setError('Coordinates must be valid numbers.')
      return
    }
    if (durationMinutes < 0 || gain < 0) {
      setError('Duration and gain cannot be negative.')
      return
    }
    onAdd({
      time,
      durationMinutes,
      gain,
      latitude: parsedLatitude,
      longitude: parsedLongitude,
    })
    setAddress('')
    setLatitude('')
    setLongitude('')
    setError(null)
  }

  return (
    <Stack spacing={1.5}>
      {error && <Alert severity="error">{error}</Alert>}
      <Stack direction="row" spacing={1}>
        <TextField
          label="Time"
          type="time"
          value={time}
          onChange={(event) => setTime(event.target.value)}
          size="small"
          fullWidth
        />
        <TextField
          label="Duration (min)"
          type="number"
          value={durationMinutes}
          onChange={(event) => setDurationMinutes(Number(event.target.value))}
          size="small"
          fullWidth
          slotProps={{ htmlInput: { min: 0 } }}
        />
        <TextField
          label="Gain"
          type="number"
          value={gain}
          onChange={(event) => setGain(Number(event.target.value))}
          size="small"
          fullWidth
          slotProps={{ htmlInput: { min: 0 } }}
        />
      </Stack>
      <LocationFields
        address={address}
        latitude={latitude}
        longitude={longitude}
        onAddressChange={setAddress}
        onLatitudeChange={setLatitude}
        onLongitudeChange={setLongitude}
      />
      <Button variant="contained" color="secondary" onClick={submit}>Add appointment</Button>
    </Stack>
  )
}
