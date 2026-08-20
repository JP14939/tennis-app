import { Alert as RNAlert, Platform } from 'react-native';

// react-native-web's Alert.alert() is a literal no-op (static alert() {}),
// so every call site using the real react-native Alert silently did nothing
// on web -- found via the "forgot password" button appearing dead, but the
// same bug affected all 21 Alert.alert call sites across the app (login-
// required prompts, delete confirmations, error messages...). This is a
// drop-in replacement with the same alert(title, message, buttons) shape --
// native behavior is untouched (forwards straight to the real Alert), web
// falls back to window.confirm/alert since there's no other synchronous
// blocking dialog available without pulling in a modal library.
function runOnWeb(title, message, buttons) {
  const list = buttons && buttons.length ? buttons : [{ text: 'OK' }];
  const body = [title, message].filter(Boolean).join('\n\n');

  if (list.length === 1) {
    window.alert(body);
    list[0].onPress?.();
    return;
  }

  const cancelIdx = list.findIndex((b) => b.style === 'cancel');
  const cancelBtn = cancelIdx >= 0 ? list[cancelIdx] : null;
  const confirmBtn = list.find((b, i) => i !== cancelIdx) || list[0];

  // window.confirm only gives a binary OK/Cancel choice -- for the rare
  // 3+ button alert, spell out the options in the message so at least
  // nothing is silently hidden, with OK mapped to the first non-cancel button.
  const prompt = list.length > 2
    ? `${body}\n\n(OK = "${confirmBtn.text || 'OK'}")`
    : body;

  if (window.confirm(prompt)) {
    confirmBtn.onPress?.();
  } else if (cancelBtn) {
    cancelBtn.onPress?.();
  }
}

const Alert = {
  alert(title, message, buttons, options) {
    if (Platform.OS === 'web') {
      runOnWeb(title, message, buttons);
      return;
    }
    RNAlert.alert(title, message, buttons, options);
  },
};

export default Alert;
