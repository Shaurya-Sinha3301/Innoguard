"""The structured output the model must return. Amounts stay strings, exactly as printed,
so the normaliser (plain code) decides how to read them."""

from pydantic import BaseModel, Field


class ExtractedValue(BaseModel):
    value: str | None = Field(description="The value exactly as printed, or null if it is absent.")
    confidence: float = Field(description="From 0 to 1, how sure you are the value is correct.")
    page: int | None = Field(description="1-based page number where the value appears, or null.")
    snippet: str | None = Field(
        description="The exact text copied from the document that shows the value, or null."
    )


class ExtractedLine(BaseModel):
    sku: str = Field(description="Item code exactly as printed.")
    qty: str = Field(description="Quantity exactly as printed.")
    unit_price: str = Field(description="Unit price exactly as printed.")
    confidence: float = Field(description="From 0 to 1, how sure you are this line is correct.")
    page: int | None = Field(description="1-based page number of the line, or null.")
    snippet: str | None = Field(description="The exact text of the line as printed, or null.")


class ExtractedInvoice(BaseModel):
    invoice_number: ExtractedValue
    vendor_id: ExtractedValue
    po_number: ExtractedValue
    currency: ExtractedValue
    subtotal: ExtractedValue
    tax: ExtractedValue
    total: ExtractedValue
    lines: list[ExtractedLine]
