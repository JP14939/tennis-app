import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { Text } from 'react-native';

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
import HighlightUploadScreen from './screens/HighlightUploadScreen';
import HighlightReviewScreen from './screens/HighlightReviewScreen';
import HighlightArchiveScreen from './screens/HighlightArchiveScreen';
import FenceTutorialScreen from './screens/FenceTutorialScreen';
import { AuthProvider } from './context/AuthContext';

const DARK   = '#0d0d0d';
const GREEN  = '#4ade80';
const BORDER = '#1e1e1e';

const TAB_ICONS = { Home: '🏠', History: '🕐', Premium: '✨', Profile: '👤' };

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: GREEN,
        tabBarInactiveTintColor: '#555',
        tabBarStyle: {
          backgroundColor: '#0a0a0a',
          borderTopColor: BORDER,
          height: 60,
          paddingBottom: 10,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        tabBarIcon: ({ focused }) => (
          <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>
            {TAB_ICONS[route.name]}
          </Text>
        ),
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="History" component={HistoryScreen} />
      <Tab.Screen name="Premium" component={PremiumScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer>
        <StatusBar style="light" />
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
          <Stack.Screen name="Upload" component={ContactMarkingScreen} options={{ title: 'Analyse Swing' }} />
          <Stack.Screen name="Results" component={ResultsScreen} options={{ title: 'Results' }} />
          <Stack.Screen name="Login" component={LoginScreen} options={{ title: 'Log In' }} />
          <Stack.Screen name="Signup" component={SignupScreen} options={{ title: 'Sign Up' }} />
          <Stack.Screen name="VersusPick" component={VersusPickScreen} options={{ title: 'Compare Videos' }} />
          <Stack.Screen name="VersusResults" component={VersusResultsScreen} options={{ title: 'Comparison' }} />
          <Stack.Screen name="HighlightUpload" component={HighlightUploadScreen} options={{ title: 'Upload Match' }} />
          <Stack.Screen name="HighlightReview" component={HighlightReviewScreen} options={{ title: 'Tag Shots' }} />
          <Stack.Screen name="HighlightArchive" component={HighlightArchiveScreen} options={{ title: 'Archive' }} />
          <Stack.Screen name="FenceTutorial" component={FenceTutorialScreen} options={{ title: 'Camera Setup' }} />
        </Stack.Navigator>
      </NavigationContainer>
    </AuthProvider>
  );
}
