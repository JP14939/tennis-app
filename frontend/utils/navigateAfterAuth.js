// Where to send the user once they've logged in or signed up. Shared by
// LoginScreen and SignupScreen so the two can't drift apart. `returnTo`, when
// set (by the onboarding guest-reveal gate in ResultsScreen), is
// `{ screen, params }` — go there so the user lands back on the thing they
// were doing; otherwise fall through to Home.
export function navigateAfterAuth(navigation, returnTo) {
  if (returnTo?.screen) {
    navigation.navigate(returnTo.screen, returnTo.params);
  } else {
    navigation.navigate('MainTabs', { screen: 'Home' });
  }
}
