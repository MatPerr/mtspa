# Random initialization and variation operators

[Documentation index](README.md)

Source: [variation_ops.py](../app/optimization/variation_ops.py).

These functions are shared by full/lite SA, loss calibration, and temperature
calibration. They work on tours and report which routes changed; they do not
compute metrics, choose acceptance, or enforce timing feasibility.

## Initialization

```text
initialize_random_tours(problem, rng)
├── [for each appointment] rng.randrange(agent_count) → assigned agent
├── [for each agent]
│   ├── appointments.sort(key=node_times.__getitem__)
│   └── [create home → sorted appointments → home]
└── [return Tours]
```

Every appointment is assigned once. Counts need not be equal across agents,
and empty routes are allowed. Sorting by time does not guarantee that travel
and service fit between visits. Ties retain the appointment input order.

## Choosing a neighbor

```text
sample_neighbor(problem, rng, tours)
├── [fewer than two agents] return None
├── rng.sample(agent_ids, k=2)           donor and receiver
├── [donor empty] exchange donor/receiver roles
├── [both empty] return None
├── [copy outer tours list and both selected routes]
├── [receiver nonempty and rng.random() < 0.5]
│   └── swap_appointments()
├── [otherwise]
│   └── give_appointment()
└── [return new tours and (donor_id, receiver_id)]
```

The 50/50 choice applies when both selected routes contain appointments. An
empty receiver forces a transfer. This is an exchange between two agents,
not a swap of two visits within one route.

## Moving appointments

```text
give_appointment(problem, rng, donor_tour, receiver_tour)
├── rng.randrange(1, len(donor_tour) - 1) → appointment position
├── donor_tour.pop(position)
└── insort_right(receiver_tour, appointment, interior bounds, key=(time, node_id))

swap_appointments(problem, rng, first_tour, second_tour)
├── [choose a random interior appointment from the first route]
├── [look for appointments with the same time in the second route]
├── [choose a same-time match if possible; otherwise any interior appointment]
├── [remove the two chosen appointments]
└── insort_right(...) into each opposite route, keyed by (time, node_id)
```

Both low-level operators mutate the routes passed to them. `sample_neighbor()`
passes copies, so the current solution remains unchanged. Home endpoints are
excluded from selection and insertion. Insertion uses binary search for the
position, but shifting Python list elements still makes insertion linear in
route length; it is not an O(log n) operation overall.

The outer list is new, the two changed route lists are new, and untouched route
lists are shared. This supports [incremental metrics](metrics.md), provided
existing solutions and unchanged routes are treated as immutable.

## Who uses the proposal?

- SA builds a candidate solution and applies its loss/temperature acceptance rule.
- Loss calibration always advances to an available neighbor in its random walk.
- Temperature calibration evaluates neighbors of one fixed solution without advancing it.
- The DP search does not call these moves; its initial weight calibration can.
