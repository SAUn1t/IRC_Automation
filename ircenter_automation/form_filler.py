import re
from dataclasses import dataclass

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout

from .errors import FieldNotFound, FieldPopulationError, VerificationError
from .mapping import FieldValue
from .normalization import comparison_key


@dataclass(frozen=True)
class VerificationResult:
    field_name: str
    expected: str
    actual: str
    match: bool


class FormFiller:
    def __init__(self, page: Page):
        self.page = page

    def _locator(self, field: FieldValue) -> Locator:
        target = self.page.locator(field.spec.selector)
        if target.count() != 1 or not target.is_visible() or not target.is_enabled():
            raise FieldNotFound(f"Website field missing, hidden, disabled, or ambiguous: {field.spec.key}")
        return target

    def _option(self, field: FieldValue) -> str:
        for document_value, website_value in field.spec.options.items():
            if comparison_key(document_value) == comparison_key(field.expected):
                return website_value
        raise FieldPopulationError(f"Unmapped website option: {field.spec.key}")

    def fill(self, field: FieldValue) -> None:
        target = self._locator(field)
        control = field.spec.control
        try:
            if control in ("text", "textarea", "date", "richtext"):
                target.fill(field.expected)
            elif control == "select":
                target.select_option(value=self._option(field))
            elif control == "checkbox":
                if field.expected == "true":
                    target.check()
                elif field.expected == "false":
                    target.uncheck()
                else:
                    raise FieldPopulationError(f"Invalid checkbox: {field.spec.key}")
            elif control == "radio":
                option = self.page.locator(self._option(field))
                if option.count() != 1 or not option.is_visible() or not option.is_enabled():
                    raise FieldNotFound(f"Radio option missing or ambiguous: {field.spec.key}")
                option.check()
            elif control == "autocomplete":
                target.fill(field.expected)
                assert field.spec.option_selector is not None
                choices = self.page.locator(field.spec.option_selector).filter(
                    has_text=re.compile(r"^\s*" + re.escape(field.expected) + r"\s*$", re.IGNORECASE)
                )
                choices.first.wait_for(state="visible")
                if choices.count() != 1:
                    raise FieldPopulationError(f"Autocomplete option ambiguous: {field.spec.key}")
                choices.click()
            else:
                raise FieldPopulationError(f"Unsupported control: {field.spec.key}")
        except (PlaywrightTimeout, ValueError) as exc:
            raise FieldPopulationError(f"Unable to populate website field: {field.spec.key}") from exc
        result = self.verify(field)
        if not result.match:
            raise VerificationError(f"Read-back mismatch after filling: {field.spec.key}")

    def verify(self, field: FieldValue) -> VerificationResult:
        target = self._locator(field)
        control = field.spec.control
        if control == "checkbox":
            actual = "true" if target.is_checked() else "false"
            expected = field.expected
        elif control == "radio":
            expected = self._option(field)
            actual = expected if self.page.locator(expected).is_checked() else ""
        elif control == "select":
            expected = self._option(field)
            actual = target.input_value()
        else:
            reader = self.page.locator(field.spec.verification_selector) if field.spec.verification_selector else target
            if reader.count() != 1:
                raise FieldNotFound(f"Verification element ambiguous: {field.spec.key}")
            actual = reader.inner_text() if field.spec.verification_mode == "text" or control == "richtext" else reader.input_value()
            expected = field.expected
        # Preserve meaningful internal spacing and line breaks; normalize platform newlines only.
        match = actual.replace("\r\n", "\n").strip() == expected.replace("\r\n", "\n").strip()
        return VerificationResult(field.spec.key, expected, actual, match)

    def verify_all(self, fields: tuple[FieldValue, ...]) -> dict[str, VerificationResult]:
        results = {field.spec.key: self.verify(field) for field in fields}
        failed = [key for key, result in results.items() if not result.match]
        if failed:
            raise VerificationError("Full verification failed for: " + ", ".join(failed))
        return results
