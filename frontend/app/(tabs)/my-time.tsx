import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import * as Haptics from "expo-haptics";

import { Assessment, fetchHistory } from "@/src/api";
import { API_BASE as BASE } from "@/src/config";
import { DEMO_ASSESSMENT_ID, demoAssessment } from "@/src/demoAssessment";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { colors, radius, spacing } from "@/src/theme";
import { loadUserPreferences } from "@/src/userPreferences";
import { storage } from "@/src/utils/storage";

const bookCover = require("@/assets/images/my-time/garden-by-the-sea.png");
const songArtwork = require("@/assets/images/my-time/name-that-song.png");
const audiobookNarration = require("@/assets/audio/my-time/garden-by-the-sea-narration.mp3");

const AUDIOBOOK_POSITION_KEY = "my_time_garden_chapter_3_position";
const CHAPTER_MINUTES = 18;
const CHAPTER_PROGRESS_AT_START = 0.64;

type RehabGameId = "garden_reach" | "lantern_trail" | "set_the_table";

type RehabGame = {
  id: RehabGameId;
  name: string;
  subtitle: string;
  objective: string;
  image: string;
  requires: "upper-limb" | "hand";
};

type RehabGameProgress = {
  completed?: boolean;
};

type GamePlanContext = {
  planId: string;
  hasPlan: boolean;
  upperLimb: boolean;
  hand: boolean;
};

const EMPTY_GAME_CONTEXT: GamePlanContext = {
  planId: "my-time",
  hasPlan: false,
  upperLimb: false,
  hand: false,
};

const GAME_PROGRESS_KEY = (planId: string, gameId: RehabGameId) => `rehab_game_progress_v1:${planId}:${gameId}`;

const REHAB_GAMES: RehabGame[] = [
  {
    id: "garden_reach",
    name: "Garden Reach",
    subtitle: "Water each flower with a gentle reach.",
    objective: "Point-to-point reaching",
    image: "/game-assets/garden-reach.png",
    requires: "upper-limb",
  },
  {
    id: "lantern_trail",
    name: "Lantern Trail",
    subtitle: "Guide the light smoothly along the path.",
    objective: "Smooth movement control",
    image: "/game-assets/lantern-trail.png",
    requires: "upper-limb",
  },
  {
    id: "set_the_table",
    name: "Set the Table",
    subtitle: "Select each item, then place it carefully.",
    objective: "Reach, hold and transfer",
    image: "/game-assets/set-the-table.png",
    requires: "hand",
  },
];

const SONGS = [
  {
    title: "Twinkle, Twinkle, Little Star",
    source: require("@/assets/audio/my-time/twinkle-twinkle.wav"),
  },
  {
    title: "Ode to Joy",
    source: require("@/assets/audio/my-time/ode-to-joy.wav"),
  },
  {
    title: "Frere Jacques",
    source: require("@/assets/audio/my-time/frere-jacques.wav"),
  },
] as const;

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

export default function MyTimeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { palette, preferences, scale } = useDisplayPreferences();
  const wide = width >= 760;
  const compact = width < 520;

  const audiobookPlayer = useAudioPlayer(audiobookNarration, { updateInterval: 500 });
  const audiobookStatus = useAudioPlayerStatus(audiobookPlayer);
  const songPlayer = useAudioPlayer(SONGS[0].source, { updateInterval: 250 });
  const songStatus = useAudioPlayerStatus(songPlayer);

  const [savedPosition, setSavedPosition] = useState(0);
  const [audiobookError, setAudiobookError] = useState("");
  const [songOpen, setSongOpen] = useState(false);
  const [songIndex, setSongIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [gameProgress, setGameProgress] = useState<Partial<Record<RehabGameId, RehabGameProgress>>>({});
  const [gameContext, setGameContext] = useState<GamePlanContext>(EMPTY_GAME_CONTEXT);
  const [gamesLoading, setGamesLoading] = useState(true);
  const lastSavedSecond = useRef(-1);
  const resumeApplied = useRef(false);

  const loadGameState = useCallback(async () => {
    setGamesLoading(true);
    const [history, savedPreferences] = await Promise.all([
      fetchHistory().catch(() => [] as Assessment[]),
      loadUserPreferences().catch(() => ({ demoMode: preferences.demoMode })),
    ]);
    const latestPlan = [...history]
      .sort((left, right) => (Date.parse(right.created_at || "") || 0) - (Date.parse(left.created_at || "") || 0))
      .find((assessment) => Array.isArray(assessment.rehab_plan) && assessment.rehab_plan.length > 0);
    const demoMode = savedPreferences.demoMode || preferences.demoMode;
    const activePlan = latestPlan || (demoMode ? demoAssessment : null);

    if (!activePlan) {
      setGameContext(EMPTY_GAME_CONTEXT);
      setGameProgress({});
      setGamesLoading(false);
      return;
    }

    const planText = activePlan.rehab_plan
      .map((exercise) => `${exercise.name} ${exercise.description} ${exercise.targets_issue}`)
      .join(" ")
      .toLowerCase();
    const planId = activePlan.id || (demoMode ? DEMO_ASSESSMENT_ID : "my-time");
    const entries = await Promise.all(REHAB_GAMES.map(async (game) => {
      const raw = await storage.getItem(GAME_PROGRESS_KEY(planId, game.id), "");
      try {
        return [game.id, raw ? JSON.parse(raw) as RehabGameProgress : {}] as const;
      } catch {
        return [game.id, {}] as const;
      }
    }));

    setGameContext({
      planId,
      hasPlan: true,
      upperLimb: /arm|shoulder|reach|trunk|upper limb|hand|finger|grip|palm|thumb/.test(planText),
      hand: /hand|finger|grip|palm|thumb|grasp|pinch/.test(planText),
    });
    setGameProgress(Object.fromEntries(entries) as Partial<Record<RehabGameId, RehabGameProgress>>);
    setGamesLoading(false);
  }, [preferences.demoMode]);

  useFocusEffect(useCallback(() => {
    void loadGameState();
  }, [loadGameState]));

  useEffect(() => {
    void storage.getItem(AUDIOBOOK_POSITION_KEY, 0).then((value) => {
      if (typeof value === "number" && Number.isFinite(value)) setSavedPosition(Math.max(0, value));
    });
  }, []);

  useEffect(() => {
    const currentSecond = Math.floor(audiobookStatus.currentTime || 0);
    if (currentSecond <= 0 || currentSecond === lastSavedSecond.current || currentSecond % 2 !== 0) return;
    lastSavedSecond.current = currentSecond;
    setSavedPosition(currentSecond);
    void storage.setItem(AUDIOBOOK_POSITION_KEY, currentSecond);
  }, [audiobookStatus.currentTime]);

  useEffect(() => {
    if (!audiobookStatus.isLoaded || resumeApplied.current || savedPosition <= 0) return;
    resumeApplied.current = true;
    const latestResumePoint = Math.max(0, (audiobookStatus.duration || savedPosition + 1) - 1);
    void audiobookPlayer.seekTo(Math.min(savedPosition, latestResumePoint)).catch(() => undefined);
  }, [audiobookPlayer, audiobookStatus.duration, audiobookStatus.isLoaded, savedPosition]);

  const toggleAudiobook = useCallback(() => {
    setAudiobookError("");
    if (audiobookStatus.playing) {
      audiobookPlayer.pause();
      return;
    }
    try {
      if (audiobookStatus.didJustFinish) {
        void audiobookPlayer.seekTo(0);
        resumeApplied.current = true;
      }
      // Keep play() inside the direct button gesture so browser autoplay
      // policies do not block the audiobook after an asynchronous seek.
      audiobookPlayer.play();
    } catch {
      setAudiobookError("The audiobook could not play. Please try again.");
    }
  }, [audiobookPlayer, audiobookStatus.didJustFinish, audiobookStatus.playing]);

  const openSongGame = () => {
    songPlayer.pause();
    songPlayer.replace(SONGS[songIndex].source);
    setSelectedAnswer(null);
    setSongOpen(true);
  };

  const toggleSong = async () => {
    if (songStatus.playing) {
      songPlayer.pause();
      return;
    }
    if (songStatus.didJustFinish) await songPlayer.seekTo(0);
    songPlayer.play();
  };

  const nextSong = () => {
    const nextIndex = (songIndex + 1) % SONGS.length;
    songPlayer.pause();
    songPlayer.replace(SONGS[nextIndex].source);
    setSongIndex(nextIndex);
    setSelectedAnswer(null);
  };

  const closeSongGame = () => {
    songPlayer.pause();
    setSongOpen(false);
  };

  const openRehabGame = (game: RehabGame) => {
    void Haptics.selectionAsync().catch(() => undefined);
    router.push({
      pathname: "/rehab-game",
      params: {
        game_id: game.id,
        name: game.name,
        plan_id: gameContext.planId,
        difficulty: "medium",
      },
    });
  };

  const chapterProgress = Math.min(0.94, CHAPTER_PROGRESS_AT_START + savedPosition / (CHAPTER_MINUTES * 60) * 0.36);
  const minutesLeft = Math.max(1, CHAPTER_MINUTES - Math.floor(savedPosition / 60));
  const answerIsCorrect = selectedAnswer === SONGS[songIndex].title;

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[styles.scrollContent, { paddingTop: insets.top + spacing.md }]}
      >
        <View style={styles.page}>
          <View style={styles.brandRow}>
            <View style={styles.brandIcon}><Ionicons name="pulse" size={23} color="#FFFFFF" /></View>
            <Text style={[styles.brandName, { color: palette.text, fontSize: 24 * scale }]}>Rehyn</Text>
          </View>

          <View style={styles.headingBlock}>
            <Text style={[styles.title, { color: palette.text, fontSize: (compact ? 42 : 56) * scale, lineHeight: (compact ? 50 : 64) * scale }]}>My Time</Text>
            <Text style={[styles.subtitle, { color: palette.text, fontSize: 19 * scale, lineHeight: 28 * scale }]}>Relax with something you enjoy.</Text>
          </View>

          <View
            testID="my-time-audiobook-card"
            style={[
              styles.audiobookCard,
              { backgroundColor: palette.surface, borderColor: palette.border },
              wide && styles.audiobookCardWide,
            ]}
          >
            <Image source={bookCover} resizeMode="cover" style={[styles.bookCover, wide && styles.bookCoverWide]} />
            <View style={[styles.audiobookCopy, wide && styles.audiobookCopyWide]}>
              <Text style={[styles.eyebrow, { color: palette.text, fontSize: 16 * scale }]}>Continue listening</Text>
              <Text style={[styles.bookTitle, { color: palette.text, fontSize: (compact ? 26 : 34) * scale, lineHeight: (compact ? 34 : 42) * scale }]}>The Garden by the Sea</Text>
              <Text style={[styles.bookMeta, { color: palette.text, fontSize: 17 * scale }]}>Chapter 3 · {minutesLeft} minutes left</Text>
              <View style={[styles.progressTrack, { backgroundColor: palette.soft }]} accessibilityLabel={`${Math.round(chapterProgress * 100)} percent complete`}>
                <View style={[styles.progressFill, { width: `${chapterProgress * 100}%` }]} />
              </View>
              <Pressable
                testID="my-time-audiobook-toggle"
                accessibilityRole="button"
                accessibilityLabel={audiobookStatus.playing ? "Pause audiobook" : "Continue audiobook"}
                onPress={() => void toggleAudiobook()}
                style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
              >
                <Ionicons name={audiobookStatus.playing ? "pause" : "play"} size={23} color="#FFFFFF" />
                <Text style={[styles.primaryButtonText, { fontSize: 18 * scale }]}>{audiobookStatus.playing ? "Pause audiobook" : "Continue audiobook"}</Text>
              </Pressable>
              {audiobookError ? <Text style={styles.errorText}>{audiobookError}</Text> : null}
            </View>
          </View>

          <View
            testID="my-time-song-card"
            style={[
              styles.songCard,
              { backgroundColor: palette.surface, borderColor: palette.border },
              wide && styles.songCardWide,
            ]}
          >
            <Image source={songArtwork} resizeMode="contain" style={styles.songArtwork} />
            <View style={styles.songCopy}>
              <Text style={[styles.songTitle, { color: palette.text, fontSize: (compact ? 27 : 32) * scale, lineHeight: (compact ? 34 : 40) * scale }]}>Name That Song</Text>
              <Text style={[styles.songSubtitle, { color: palette.text, fontSize: 17 * scale, lineHeight: 25 * scale }]}>Listen to a clip and choose the song.</Text>
              <Pressable testID="my-time-open-song-game" onPress={openSongGame} style={({ pressed }) => [styles.songButton, pressed && styles.pressed]}>
                <Ionicons name="musical-notes" size={22} color="#FFFFFF" />
                <Text style={[styles.songButtonText, { fontSize: 18 * scale }]}>Play</Text>
              </Pressable>
            </View>
          </View>

          <View testID="rehab-games-section" style={[styles.gamesSection, { borderTopColor: palette.border }]}>
            <View style={styles.gamesHeadingRow}>
              <View style={styles.gamesHeadingCopy}>
                <Text style={[styles.gamesEyebrow, { color: palette.brand, fontSize: 12 * scale }]}>Move and play</Text>
                <Text style={[styles.gamesTitle, { color: palette.text, fontSize: (compact ? 29 : 34) * scale, lineHeight: (compact ? 37 : 42) * scale }]}>Movement games</Text>
                <Text style={[styles.gamesIntro, { color: palette.muted, fontSize: 16 * scale, lineHeight: 24 * scale }]}>Enjoy a short camera-guided activity matched to the movement focus in your current plan.</Text>
              </View>
              <View style={[styles.voiceTag, { backgroundColor: palette.soft, borderColor: palette.border }]}>
                <Ionicons name="volume-high-outline" size={20} color={palette.brand} />
                <Text style={[styles.voiceTagText, { color: palette.text, fontSize: 13 * scale }]}>Voice guided</Text>
              </View>
            </View>

            <View style={[styles.gameSafetyNote, { backgroundColor: palette.soft, borderColor: palette.border }]}>
              <Ionicons name="accessibility-outline" size={23} color={palette.brand} />
              <Text style={[styles.gameSafetyNoteText, { color: palette.text, fontSize: 14 * scale, lineHeight: 21 * scale }]}>Play seated in a stable chair, keep your usual support nearby, and stay within a comfortable movement range. Complete your initial assessment to unlock games that suit your plan.</Text>
            </View>

            {gamesLoading ? (
              <View style={styles.gamesLoading} testID="rehab-games-loading">
                <ActivityIndicator size="small" color={palette.brand} />
                <Text style={[styles.gamesLoadingText, { color: palette.muted }]}>Matching games to your plan...</Text>
              </View>
            ) : (
              <View style={[styles.gameGrid, wide && styles.gameGridWide]}>
                {REHAB_GAMES.map((game) => {
                  const saved = gameProgress[game.id];
                  const isSuitable = gameContext.hasPlan && (game.requires === "hand" ? gameContext.hand : gameContext.upperLimb);
                  const lockedLabel = gameContext.hasPlan ? "Not in current plan" : "Assessment needed";
                  return (
                    <View
                      key={game.id}
                      testID={`rehab-game-${game.id}`}
                      style={[
                        styles.gameCard,
                        { backgroundColor: palette.surface, borderColor: saved?.completed ? palette.brand : palette.border },
                        wide && styles.gameCardWide,
                      ]}
                    >
                      <View style={[styles.gameImageWrap, { backgroundColor: palette.soft }]}>
                        <Image
                          source={{ uri: Platform.OS === "web" ? game.image : `${BASE}${game.image}` }}
                          style={styles.gameImage}
                          resizeMode="cover"
                          accessibilityLabel={`${game.name} game scene`}
                        />
                        {saved?.completed ? (
                          <View style={styles.gameCompleteBadge} testID={`rehab-game-complete-${game.id}`}>
                            <Ionicons name="checkmark" size={16} color="#FFFFFF" />
                            <Text style={styles.gameCompleteBadgeText}>Played</Text>
                          </View>
                        ) : null}
                      </View>
                      <View style={styles.gameBody}>
                        <View style={[styles.gameObjectiveTag, { backgroundColor: palette.soft }]}>
                          <Text style={[styles.gameObjectiveTagText, { color: palette.brand, fontSize: 11 * scale }]}>{game.objective}</Text>
                        </View>
                        <Text style={[styles.gameTitle, { color: palette.text, fontSize: 21 * scale, lineHeight: 27 * scale }]}>{game.name}</Text>
                        <Text style={[styles.gameSubtitle, { color: palette.muted, fontSize: 14 * scale, lineHeight: 21 * scale }]}>{game.subtitle}</Text>
                        <Pressable
                          disabled={!isSuitable}
                          onPress={() => openRehabGame(game)}
                          accessibilityRole="button"
                          accessibilityLabel={`${isSuitable ? (saved?.completed ? "Play again" : "Play") : lockedLabel}: ${game.name}`}
                          testID={`play-game-${game.id}`}
                          style={({ pressed }) => [
                            styles.gameButton,
                            { backgroundColor: isSuitable ? "#075D40" : palette.soft, borderColor: isSuitable ? "#075D40" : palette.border },
                            pressed && isSuitable && styles.pressed,
                          ]}
                        >
                          <Ionicons name={isSuitable ? "game-controller-outline" : "lock-closed-outline"} size={21} color={isSuitable ? "#FFFFFF" : palette.muted} />
                          <Text style={[styles.gameButtonText, { color: isSuitable ? "#FFFFFF" : palette.muted, fontSize: 15 * scale }]}>{isSuitable ? (saved?.completed ? "Play again" : "Play game") : lockedLabel}</Text>
                        </Pressable>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        </View>
      </ScrollView>

      <Modal visible={songOpen} transparent animationType="fade" onRequestClose={closeSongGame}>
        <View style={styles.modalScrim}>
          <View style={[styles.gameModal, { backgroundColor: palette.surface, borderColor: palette.border, paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
            <View style={styles.modalHeader}>
              <View>
                <Text style={[styles.modalTitle, { color: palette.text, fontSize: 25 * scale }]}>Name That Song</Text>
                <Text style={[styles.modalLead, { color: palette.muted, fontSize: 15 * scale }]}>Clip {songIndex + 1} of {SONGS.length}</Text>
              </View>
              <Pressable accessibilityLabel="Close song game" onPress={closeSongGame} style={[styles.iconButton, { borderColor: palette.border }]}>
                <Ionicons name="close" size={24} color={palette.text} />
              </Pressable>
            </View>

            <View style={[styles.listenPanel, { backgroundColor: palette.soft }]}>
              <View style={[styles.musicDisc, { backgroundColor: palette.surface }]}><Ionicons name="musical-note" size={33} color={palette.brand} /></View>
              <View style={styles.listenCopy}>
                <Text style={[styles.listenTitle, { color: palette.text }]}>Listen to the melody</Text>
                <Text style={[styles.listenTime, { color: palette.muted }]}>{formatTime(songStatus.currentTime)} / {formatTime(songStatus.duration)}</Text>
              </View>
              <Pressable testID="my-time-song-toggle" accessibilityLabel={songStatus.playing ? "Pause song clip" : "Play song clip"} onPress={() => void toggleSong()} style={styles.roundPlayButton}>
                <Ionicons name={songStatus.playing ? "pause" : "play"} size={25} color="#FFFFFF" />
              </Pressable>
            </View>

            <Text style={[styles.answerPrompt, { color: palette.text, fontSize: 17 * scale }]}>Which song did you hear?</Text>
            <View style={styles.answerList}>
              {SONGS.map((song) => {
                const selected = selectedAnswer === song.title;
                const correct = selected && song.title === SONGS[songIndex].title;
                const wrong = selected && !correct;
                return (
                  <Pressable
                    key={song.title}
                    testID={`my-time-answer-${song.title}`}
                    disabled={Boolean(selectedAnswer)}
                    onPress={() => setSelectedAnswer(song.title)}
                    style={[
                      styles.answerButton,
                      { borderColor: palette.border, backgroundColor: palette.surface },
                      correct && styles.answerCorrect,
                      wrong && styles.answerWrong,
                    ]}
                  >
                    <Text style={[styles.answerText, { color: palette.text, fontSize: 16 * scale }]}>{song.title}</Text>
                    {selected ? <Ionicons name={correct ? "checkmark-circle" : "close-circle"} size={23} color={correct ? colors.success : colors.error} /> : null}
                  </Pressable>
                );
              })}
            </View>

            {selectedAnswer ? (
              <View style={[styles.feedback, { backgroundColor: answerIsCorrect ? "#EAF5ED" : "#FFF3EF" }]}>
                <Ionicons name={answerIsCorrect ? "sparkles" : "refresh-circle-outline"} size={22} color={answerIsCorrect ? colors.success : colors.error} />
                <Text style={[styles.feedbackText, { color: answerIsCorrect ? "#245E39" : "#8B3D32" }]}>{answerIsCorrect ? "You got it. Nicely remembered." : `That was ${SONGS[songIndex].title}.`}</Text>
              </View>
            ) : null}

            <Pressable disabled={!selectedAnswer} testID="my-time-next-song" onPress={nextSong} style={[styles.nextButton, !selectedAnswer && styles.disabled]}>
              <Text style={styles.nextButtonText}>Next clip</Text>
              <Ionicons name="arrow-forward" size={20} color="#FFFFFF" />
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  scrollContent: { paddingHorizontal: spacing.md, paddingBottom: 120 },
  page: { width: "100%", maxWidth: 1040, alignSelf: "center", gap: spacing.lg },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brandIcon: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: "#075D40", alignItems: "center", justifyContent: "center" },
  brandName: { fontWeight: "900" },
  headingBlock: { gap: spacing.xs, marginTop: spacing.sm },
  title: { fontWeight: "900" },
  subtitle: { fontWeight: "500" },
  audiobookCard: { borderWidth: 1, borderRadius: radius.sm, padding: spacing.lg, gap: spacing.lg, alignItems: "center" },
  audiobookCardWide: { flexDirection: "row", alignItems: "stretch", padding: spacing.xl },
  bookCover: { width: 190, height: 285, borderRadius: radius.sm, backgroundColor: "#EAF0EC" },
  bookCoverWide: { width: 254, height: 381 },
  audiobookCopy: { flex: 1, width: "100%", justifyContent: "center", gap: spacing.md },
  audiobookCopyWide: { width: "auto" },
  eyebrow: { fontWeight: "800" },
  bookTitle: { fontWeight: "900" },
  bookMeta: { fontWeight: "500" },
  progressTrack: { height: 16, borderRadius: radius.sm, overflow: "hidden", marginTop: spacing.xs },
  progressFill: { height: "100%", borderRadius: radius.sm, backgroundColor: "#9FBEA2" },
  primaryButton: { minHeight: 58, borderRadius: radius.sm, backgroundColor: "#075D40", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg, marginTop: spacing.sm },
  primaryButtonText: { color: "#FFFFFF", fontWeight: "900", textAlign: "center" },
  errorText: { color: colors.error, fontSize: 13, lineHeight: 19, fontWeight: "700", textAlign: "center" },
  songCard: { borderWidth: 1, borderRadius: radius.sm, padding: spacing.lg, gap: spacing.lg, alignItems: "center" },
  songCardWide: { flexDirection: "row", paddingHorizontal: spacing.xl, paddingVertical: spacing.lg },
  songArtwork: { width: 220, height: 180 },
  songCopy: { flex: 1, width: "100%", gap: spacing.sm, justifyContent: "center" },
  songTitle: { fontWeight: "900" },
  songSubtitle: { fontWeight: "500" },
  songButton: { width: "100%", maxWidth: 360, minHeight: 54, borderRadius: radius.sm, backgroundColor: "#075D40", flexDirection: "row", gap: spacing.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.xs },
  songButtonText: { color: "#FFFFFF", fontWeight: "900" },
  gamesSection: { marginTop: spacing.md, paddingTop: spacing.xl, borderTopWidth: 1 },
  gamesHeadingRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.md },
  gamesHeadingCopy: { flex: 1, minWidth: 250, maxWidth: 720 },
  gamesEyebrow: { fontWeight: "900", textTransform: "uppercase", letterSpacing: 0 },
  gamesTitle: { marginTop: 3, fontWeight: "900", letterSpacing: 0 },
  gamesIntro: { marginTop: spacing.xs, fontWeight: "500" },
  voiceTag: { minHeight: 42, flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingHorizontal: spacing.md, borderWidth: 1, borderRadius: radius.sm },
  voiceTagText: { fontWeight: "900" },
  gameSafetyNote: { marginTop: spacing.lg, flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderRadius: radius.sm },
  gameSafetyNoteText: { flex: 1, fontWeight: "600" },
  gamesLoading: { minHeight: 160, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  gamesLoadingText: { fontSize: 14, lineHeight: 20, fontWeight: "700" },
  gameGrid: { marginTop: spacing.lg, gap: spacing.md },
  gameGridWide: { flexDirection: "row", alignItems: "stretch" },
  gameCard: { borderWidth: 1, borderRadius: radius.sm, overflow: "hidden" },
  gameCardWide: { flex: 1, minWidth: 0 },
  gameImageWrap: { position: "relative", width: "100%", aspectRatio: 1.5, overflow: "hidden" },
  gameImage: { width: "100%", height: "100%" },
  gameCompleteBadge: { position: "absolute", top: spacing.sm, right: spacing.sm, minHeight: 32, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.sm, borderRadius: radius.sm, backgroundColor: "#2B7547" },
  gameCompleteBadgeText: { fontSize: 12, lineHeight: 16, fontWeight: "900", color: "#FFFFFF" },
  gameBody: { flex: 1, padding: spacing.md },
  gameObjectiveTag: { alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.sm },
  gameObjectiveTagText: { fontWeight: "900" },
  gameTitle: { marginTop: spacing.sm, fontWeight: "900" },
  gameSubtitle: { minHeight: 44, marginTop: 4, fontWeight: "500" },
  gameButton: { minHeight: 50, marginTop: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.md, borderWidth: 1, borderRadius: radius.sm },
  gameButtonText: { fontWeight: "900", textAlign: "center" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.99 }] },
  disabled: { opacity: 0.45 },
  modalScrim: { flex: 1, backgroundColor: "rgba(11, 24, 18, 0.58)", justifyContent: "center", alignItems: "center", padding: spacing.md },
  gameModal: { width: "100%", maxWidth: 600, maxHeight: "92%", borderWidth: 1, borderRadius: radius.sm, padding: spacing.lg, gap: spacing.md },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.md },
  modalTitle: { fontWeight: "900" },
  modalLead: { fontWeight: "700", marginTop: 3 },
  iconButton: { width: 44, height: 44, borderWidth: 1, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  listenPanel: { minHeight: 82, borderRadius: radius.sm, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md },
  musicDisc: { width: 54, height: 54, borderRadius: 27, alignItems: "center", justifyContent: "center" },
  listenCopy: { flex: 1, gap: 4 },
  listenTitle: { fontSize: 16, fontWeight: "900" },
  listenTime: { fontSize: 13, fontWeight: "700" },
  roundPlayButton: { width: 52, height: 52, borderRadius: 26, backgroundColor: "#075D40", alignItems: "center", justifyContent: "center" },
  answerPrompt: { fontWeight: "900" },
  answerList: { gap: spacing.sm },
  answerButton: { minHeight: 54, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  answerCorrect: { borderColor: colors.success, backgroundColor: "#F1F8F3" },
  answerWrong: { borderColor: colors.error, backgroundColor: "#FFF7F4" },
  answerText: { flex: 1, fontWeight: "700" },
  feedback: { borderRadius: radius.sm, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  feedbackText: { flex: 1, fontSize: 14, lineHeight: 20, fontWeight: "800" },
  nextButton: { minHeight: 54, borderRadius: radius.sm, backgroundColor: "#075D40", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  nextButtonText: { color: "#FFFFFF", fontSize: 17, fontWeight: "900" },
});
