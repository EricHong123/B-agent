import { ElMessageBox } from 'element-plus'
import { translate } from '@/i18n'

/** Ask for a short free-text reason; resolves to null when the user cancels. */
export async function promptText(
  message: string,
  title: string,
  options: { inputValue?: string, validator?: (value: string) => boolean } = {}
) {
  try {
    const result = await ElMessageBox.prompt(translate(message), translate(title), {
      inputValue: options.inputValue,
      inputValidator: options.validator ?? ((value: string) => value.trim().length >= 3),
      confirmButtonText: translate('Confirm'),
      cancelButtonText: translate('Cancel'),
    }) as { value: string }
    return result.value.trim()
  } catch {
    return null
  }
}
