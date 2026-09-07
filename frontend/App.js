import './utils/installFetchShim'; // must run before any api/* fetch — see file
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import {
  useFonts,
  Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import { InstrumentSerif_400Regular, InstrumentSerif_400Regular_Italic } from '@expo-google-fonts/instrument-serif';

import FloatingTabBar from './components/FloatingTabBar';
import { colors } from './theme';
// Native (iOS/Android) RevenueCat init is prepared but parked -- see
// components/PremiumCheckout.native.ready.js for why and how to activate.
// import { initPurchases } from './services/purchasesInit';
import HomeScreen from './screens/HomeScreen';
import HistoryScreen from './screens/HistoryScreen';
import PremiumScreen from './screens/PremiumScreen';
import ProfileScreen from './screens/ProfileScreen';
import LoginScreen from './screens/LoginScreen';
import SignupScreen from './screens/SignupScreen';
import ForgotPasswordScreen from './screens/ForgotPasswordScreen';
import ContactMarkingScreen from './screens/ContactMarkingScreen';
import ResultsScreen from './screens/ResultsScreen';
import VersusPickScreen from './screens/VersusPickScreen';
import VersusResultsScreen from './screens/VersusResultsScreen';
import SyncCompareScreen from './screens/SyncCompareScreen';
import HighlightUploadScreen from './screens/HighlightUploadScreen';
import HighlightReviewScreen from './screens/HighlightReviewScreen';
import HighlightArchiveScreen from './screens/HighlightArchiveScreen';
import FenceTutorialScreen from './screens/FenceTutorialScreen';
import SettingsScreen from './screens/SettingsScreen';
import CoachScreen from './screens/CoachScreen';
import FindGamesScreen from './screens/FindGamesScreen';
import MyWatchesScreen from './screens/MyWatchesScreen';
import FriendsScreen from './screens/FriendsScreen';
import MessageThreadScreen from './screens/MessageThreadScreen';
import DevDashboardScreen from './screens/DevDashboardScreen';
import DevMLStatusScreen from './screens/DevMLStatusScreen';
import DevRallyJobsScreen from './screens/DevRallyJobsScreen';
import LessonDetailScreen from './screens/LessonDetailScreen';
import DevDrillsEditorScreen from './screens/DevDrillsEditorScreen';
import DevRallyBoundaryReviewScreen from './screens/DevRallyBoundaryReviewScreen';
import DevSwingReviewScreen from './screens/DevSwingReviewScreen';
import DevTipReviewScreen from './screens/DevTipReviewScreen';
import DevProClipReviewScreen from './screens/DevProClipReviewScreen';
import DevBallLabelScreen from './screens/DevBallLabelScreen';
import { AuthProvider } from './context/AuthContext';

const DARK   = '#0d0d0d';
const GREEN  = '#4ade80';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{ headerShown: false }}
      tabBar={(props) => <FloatingTabBar {...props} />}
    >
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="History" component={HistoryScreen} />
      <Tab.Screen name="Friends" component={FriendsScreen} />
      <Tab.Screen name="FindGames" component={FindGamesScreen} options={{ tabBarLabel: 'Find Games' }} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

export default function App() {
  const [fontsLoaded] = useFonts({
    Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold,
    InstrumentSerif_400Regular, InstrumentSerif_400Regular_Italic,
  });

  if (!fontsLoaded) {
    return <View style={{ flex: 1, backgroundColor: colors.bg }} />;
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <AuthProvider>
        <NavigationContainer>
          <StatusBar style="dark" />
          <Stack.Navigator
            screenOptions={{
              headerStyle: { backgroundColor: DARK },
              headerTintColor: GREEN,
              headerTitleStyle: { color: '#fff', fontWeight: '700', fontSize: 16 },
              headerShadowVisible: false,
              headerBackTitleVisible: false,
            }}
          >
            <Stack.Screen name="MainTabs" component={MainTabs} options={{ headerShown: false }} />
            <Stack.Screen name="Upload" component={ContactMarkingScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Results" component={ResultsScreen} options={{ headerShown: false }} />
            <Stack.Screen name="LessonDetail" component={LessonDetailScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Login" component={LoginScreen} options={{ title: 'Log In' }} />
            <Stack.Screen name="Signup" component={SignupScreen} options={{ title: 'Sign Up' }} />
            <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} options={{ title: 'Reset Password' }} />
            <Stack.Screen name="VersusPick" component={VersusPickScreen} options={{ title: 'Compare Videos' }} />
            <Stack.Screen name="VersusResults" component={VersusResultsScreen} options={{ title: 'Comparison' }} />
            <Stack.Screen name="SyncCompare" component={SyncCompareScreen} options={{ headerShown: false }} />
            <Stack.Screen name="HighlightUpload" component={HighlightUploadScreen} options={{ title: 'Upload Match' }} />
            <Stack.Screen name="HighlightReview" component={HighlightReviewScreen} options={{ title: 'Tag Shots' }} />
            <Stack.Screen name="HighlightArchive" component={HighlightArchiveScreen} options={{ title: 'Archive' }} />
            <Stack.Screen name="FenceTutorial" component={FenceTutorialScreen} options={{ title: 'Camera Setup' }} />
            <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
            <Stack.Screen name="Coach" component={CoachScreen} options={{ title: 'Coach Mode' }} />
            <Stack.Screen name="MyWatches" component={MyWatchesScreen} options={{ title: 'My Watches' }} />
            {/* Premium used to be registered both here AND as a tab
                (MainTabs above) -- that dual registration meant
                navigate('Premium') from a screen on this stack (e.g.
                ResultsScreen) resolved to THIS one instead of the tabbed
                version, landing on a headered screen with no floating tab
                bar (worked around at the time via navigate('MainTabs',
                { screen: 'Premium' })). Premium is no longer a tab at all
                (its features live on Home now, see PremiumFeaturesSection),
                so it's a single ordinary top-level screen like Settings/
                Coach below -- no more ambiguity, every navigate('Premium')
                call site (including the ones that used to need the
                MainTabs workaround) just targets this directly now. */}
            <Stack.Screen name="Premium" component={PremiumScreen} options={{ title: 'Premium' }} />
            <Stack.Screen name="MessageThread" component={MessageThreadScreen} options={{ headerShown: false }} />
            {/* Hidden dev tools (Profile -> Settings -> Dev Page) -- gated by
                frontend/utils/isAdmin.js on the entry point only; real access
                control is server-side (every /api/dev/* route requires
                requireAdmin). Registered as ordinary flat Stack.Screens like
                everything else here, not a separate navigator. */}
            <Stack.Screen name="DevDashboard" component={DevDashboardScreen} options={{ title: 'Dev Page' }} />
            <Stack.Screen name="DevMLStatus" component={DevMLStatusScreen} options={{ title: 'ML Reliability' }} />
            <Stack.Screen name="DevRallyJobs" component={DevRallyJobsScreen} options={{ title: 'Rally Boundary Review' }} />
            <Stack.Screen name="DevRallyBoundaryReview" component={DevRallyBoundaryReviewScreen} options={{ title: 'Review Boundaries' }} />
            <Stack.Screen name="DevSwingReview" component={DevSwingReviewScreen} options={{ title: 'Swing Review' }} />
            <Stack.Screen name="DevTipReview" component={DevTipReviewScreen} options={{ title: 'Tip Review' }} />
            <Stack.Screen name="DevProClipReview" component={DevProClipReviewScreen} options={{ title: 'Pro Clip Review' }} />
            <Stack.Screen name="DevBallLabel" component={DevBallLabelScreen} options={{ title: 'Ball Label' }} />
            <Stack.Screen name="DevDrillsEditor" component={DevDrillsEditorScreen} options={{ title: 'Drills & Lessons Editor' }} />
          </Stack.Navigator>
        </NavigationContainer>
      </AuthProvider>
    </GestureHandlerRootView>
  );
}
