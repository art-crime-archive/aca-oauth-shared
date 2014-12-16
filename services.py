from protorpc.wsgi import service

import archiveservice

# Map the RPC service and path (/ArchiveService)
app = service.service_mappings([('/ArchiveService', archiveservice.ArchiveService)])