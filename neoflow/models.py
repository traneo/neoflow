from pydantic import BaseModel


class TicketMetadata(BaseModel):
    title: str | None = None
    status: str | None = None
    url: str


class Ticket(BaseModel):
    metadata: TicketMetadata
    question: str | None = None
    comments: list[str] = []

    @property
    def reference(self) -> str:
        """Extract the sdk-XXXXX reference from the URL."""
        return self.metadata.url.rstrip("/").split("/")[-1]
