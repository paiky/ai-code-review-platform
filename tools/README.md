# Local JDK

This directory can hold a local JDK for inspecting the legacy Java backend in `backend/`.

Recommended layout on Windows:

```text
tools/
  jdk-21/
    bin/
      java.exe
```

The active backend is Python/FastAPI. Its `scripts/run-backend.ps1` entry point uses Python and does not require a JDK. Local JDK binaries are ignored by Git.
