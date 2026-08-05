import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import {
  useFonts,
  Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import { InstrumentSerif_400Regular, InstrumentSerif_400Regular_Italic } from '@expo-google-fonts/instrument-serif';

import FloatingTabBar from './components/FloatingTabBar';
import { colors } from './theme';
import HomeScreen from './screens/HomeScreen';
import HistoryScreen from './screens/HistoryScreen';
import PremiumScreen from './screens/PremiumScreen';
import ProfileScreen from './screens/ProfileScreen';
import LoginScreen from './screens/LoginScreen';
import SignupScreen from './screens/SignupScreen';
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
      <Tab.Screen name="Premium" component={PremiumScreen} />
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
          <Stack.Screen name="Login" component={LoginScreen} options={{ title: 'Log In' }} />
          <Stack.Screen name="Signup" component={SignupScreen} options={{ title: 'Sign Up' }} />
          <Stack.Screen name="VersusPick" component={VersusPickScreen} options={{ title: 'Compare Videos' }} />
          <Stack.Screen name="VersusResults" component={VersusResultsScreen} options={{ title: 'Comparison' }} />
          <Stack.Screen name="SyncCompare" component={SyncCompareScreen} options={{ headerShown: false }} />
          <Stack.Screen name="HighlightUpload" component={HighlightUploadScreen} options={{ title: 'Upload Match' }} />
          <Stack.Screen name="HighlightReview" component={HighlightReviewScreen} options={{ title: 'Tag Shots' }} />
          <Stack.Screen name="HighlightArchive" component={HighlightArchiveScreen} options={{ title: 'Archive' }} />
          <Stack.Screen name="FenceTutorial" component={FenceTutorialScreen} options={{ title: 'Camera Setup' }} />
          <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
        </Stack.Navigator>
      </NavigationContainer>
    </AuthProvider>
  );
}
