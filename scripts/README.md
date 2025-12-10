# Build Minecraft Images Script

Python script to build Minecraft Docker images for game projects with parallel builds and Docker Compose integration.

## Installation

Install required Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 scripts/build-minecraft-images.py
```

The script will:
1. Ask if you want to use a local local-engine JAR (optional)
2. Prompt you to enter project paths interactively

### Example

```bash
$ python3 scripts/build-minecraft-images.py
Use local local-engine JAR? (leave empty to download from GitHub):
  Local JAR path: ./local-engine/build/libs/local-engine-1.0.0.jar

Enter project paths (one per line, empty line to finish):
  Project 1: ./skyblock/player-planets
  Project 2: ./skyblock/marketplace
  Project 3: ./skyblock/exploration
  Project 4: 
```

### Using Local JAR

If you have a local build of local-engine, you can specify the path to the JAR file. This is useful for:
- Testing local changes before releasing
- Using a specific version
- Offline development

Leave the path empty to download the latest release from GitHub.

## Features

- **Parallel Builds**: Builds multiple projects simultaneously for faster execution
- **Automatic Plugin Downloads**: Downloads local-engine and dependencies from game-properties.yaml
- **Docker Compose Integration**: Automatically updates docker-compose.yml and starts services
- **Port Management**: Each project gets a unique port starting from 25565
- **Asset & Config Copying**: Automatically copies assets and configs to correct locations

## What It Does

1. **Downloads local-engine**: Gets the latest release from GitHub
2. **Builds Project JAR**: Runs `buildPluginJar` Gradle task
3. **Downloads Dependencies**: Parses `config/game-properties.yaml` and downloads:
   - PROTOCOLLIB
   - LIBSDISGUISES
   - DECENTHOLOGRAMS
4. **Copies Assets & Configs**: Copies project assets and configs to Docker image
5. **Creates Dockerfile**: Generates Dockerfile using `itzg/minecraft-server` base image
6. **Builds Docker Image**: Creates Docker image for each project
7. **Updates docker-compose.yml**: Adds services to existing docker-compose.yml
8. **Starts Services**: Automatically runs `docker-compose up -d`

## Port Assignment

Each project gets a unique port:
- First project: `25565`
- Second project: `25566`
- Third project: `25567`
- And so on...

## Project Requirements

Your project should have:
- `config/game-properties.yaml` - Game configuration with dependencies
- `build.gradle.kts` - Gradle build file with `buildPluginJar` task
- `assets/` (optional) - World templates and other assets
- `config/` (optional) - Game configuration files

## Output

The script:
- Creates Docker images named `local-minecraft-<project-name>:latest`
- Updates `docker-compose.yml` with new services
- Starts all services automatically

## Troubleshooting

### Missing Dependencies

If you get import errors, install dependencies:
```bash
pip install -r requirements.txt
```

### Build Failures

Check that:
- Project has `gradlew` or `gradlew.bat`
- `config/game-properties.yaml` exists
- Project builds successfully with `./gradlew buildPluginJar`

### Docker Issues

Ensure Docker and docker-compose are installed and running:
```bash
docker --version
docker-compose --version
```

