FROM eclipse-temurin:17-jre-jammy

# Set working directory
WORKDIR /app

# Download latest Velocity 3.4.0-SNAPSHOT build (latest version, supports Minecraft up to 1.21.10)
RUN apt-get update && \
    apt-get install -y curl python3 && \
    VERSION="3.4.0-SNAPSHOT" && \
    BUILD=$(curl -s "https://api.papermc.io/v2/projects/velocity/versions/$VERSION/builds" | python3 -c "import sys, json; data = json.load(sys.stdin); builds = data.get('builds', []); print(builds[-1]['build'] if builds else '1')") && \
    DOWNLOAD_NAME=$(curl -s "https://api.papermc.io/v2/projects/velocity/versions/$VERSION/builds/$BUILD" | python3 -c "import sys, json; data = json.load(sys.stdin); app = data.get('downloads', {}).get('application', {}); print(app.get('name', f'velocity-$VERSION-$BUILD.jar'))") && \
    curl -L -o /app/velocity.jar "https://api.papermc.io/v2/projects/velocity/versions/$VERSION/builds/$BUILD/downloads/$DOWNLOAD_NAME" && \
    test -f /app/velocity.jar && test -s /app/velocity.jar && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Expose Velocity port
EXPOSE 25565

# Set JVM options
ENV JAVA_OPTS="-Xms1G -Xmx1G -XX:+UseG1GC -XX:G1HeapRegionSize=4M -XX:+UnlockExperimentalVMOptions -XX:+ParallelRefProcEnabled -XX:+AlwaysPreTouch -XX:MaxInlineLevel=15"

# Set working directory to /config (where volume is mounted)
WORKDIR /config

# Run Velocity from /config directory
CMD ["sh", "-c", "cd /config && java $JAVA_OPTS -jar /app/velocity.jar"]

