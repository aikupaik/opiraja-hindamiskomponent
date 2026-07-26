# A junior developer's thoughts on this project
This pilot MVP plan should be feasible for a solo junior developer. As the developer learns and gains more experience, the project will also grow accordingly, but right now the goal is to get something up and running for presentation.

## Architecture
A rough idea I have come up with is:
- Keep R as the calculation service for generating KST knowledge spaces and adaptive testing. The actual test logic.
- Build a FastAPI interface as an abstraction between business logic and R test logic. This is the orchestrator. The test player gets its data and test logic through the API. Only the Python backend talks to R services.
- Prefer modular monolith for the Python backend.
- Build a lightweight React frontend test player that displays the questions one-by-one and sends back the answer. The frontend should not contain any business or test logic such as answer keys, adaptive logic, etc. The external service "õpirada" could give the student a link that directs to the test player webpage for starting the test. The actual integration is not the main concern right now, we just need a frontend UI to play the tests for the MVP.
- Defer websockets or messaging in this phase. Use HTTP and service method calls.

## Deployment
This project will be deployed on a virtual machine inside Docker containers. A little bit about that is written in the "HK_skeemid_ja_R_elemendid.md".
- The current model does not yet account for my planned architecture. You can take the current deployment idea as a baseline and append that do accomodate the final architecture.

## Data model
Try to follow "supabase_andmemudel.md". The data model should remain unchanged unless absolutely necessary for pilot development. If so, provide concrete recommendations, don't silently assume changes.
The database will stay in Supabase for now. This means you can use the Supabase SDK. However, I would prefer it, if you built a database interface, where supabase is just one of the implementations for this interface so that we could later switch to a self-hosted PostgreSQL instance instead.

## Authentication & authorization
Keep it very simple for now.