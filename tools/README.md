# Local JDK

This directory is reserved for a local JDK used by development scripts.

Recommended layout on Windows:

```text
tools/
  jdk-21/
    bin/
      java.exe
```

The `scripts/run-backend.ps1` script prefers this local JDK 21 when running the Spring Boot backend. The actual JDK binaries are intentionally ignored by Git because they are large, platform-specific, and should be updated independently.
