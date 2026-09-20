import { useEffect, useState } from 'react'
import { Alert, Button, Stack, TextField } from '@mui/material'
import type { AgentDraft, Coordinate } from '../../types'
import { LocationFields } from './LocationFields'

type AgentFormProps = {
  pickedLocation: Coordinate | null
  nextAgentNumber: number
  onAdd: (agent: Omit<AgentDraft, 'id'>) => void
}

export function AgentForm({ pickedLocation, nextAgentNumber, onAdd }: AgentFormProps) {
  const [name, setName] = useState(`Agent ${nextAgentNumber}`)
  const [startTime, setStartTime] = useState('08:00')
  const [endTime, setEndTime] = useState('18:00')
  const [address, setAddress] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setName(`Agent ${nextAgentNumber}`)
  }, [nextAgentNumber])

  useEffect(() => {
    if (!pickedLocation) return
    setAddress('')
    setLatitude(pickedLocation.latitude.toFixed(6))
    setLongitude(pickedLocation.longitude.toFixed(6))
  }, [pickedLocation])

  const submit = () => {
    const parsedLatitude = Number(latitude)
    const parsedLongitude = Number(longitude)
    if (!name.trim() || latitude === '' || longitude === '') {
      setError('Name and home coordinates are required. Find an address or click the map.')
      return
    }
    if (!Number.isFinite(parsedLatitude) || !Number.isFinite(parsedLongitude)) {
      setError('Coordinates must be valid numbers.')
      return
    }
    if (endTime <= startTime) {
      setError('End time must be after start time.')
      return
    }
    onAdd({
      name: name.trim(),
      startTime,
      endTime,
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
      <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} size="small" />
      <Stack direction="row" spacing={1}>
        <TextField
          label="Start"
          type="time"
          value={startTime}
          onChange={(event) => setStartTime(event.target.value)}
          size="small"
          fullWidth
        />
        <TextField
          label="End"
          type="time"
          value={endTime}
          onChange={(event) => setEndTime(event.target.value)}
          size="small"
          fullWidth
        />
      </Stack>
      <LocationFields
        title="Home address"
        address={address}
        latitude={latitude}
        longitude={longitude}
        onAddressChange={setAddress}
        onLatitudeChange={setLatitude}
        onLongitudeChange={setLongitude}
      />
      <Button variant="contained" onClick={submit}>Add agent</Button>
    </Stack>
  )
}
