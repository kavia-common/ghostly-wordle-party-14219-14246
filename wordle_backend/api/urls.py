from django.urls import path
from .views import (
    health,
    RegisterView,
    LoginView,
    LogoutView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    NewGameView,
    CurrentGameView,
    SubmitGuessView,
    RevealAnswerView,
    MeView,
    MyHistoryView,
    LeaderboardView,
    EffectTriggerView,
)

urlpatterns = [
    path('health/', health, name='Health'),
    # Auth
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('auth/password-reset-confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    # Gameplay
    path('game/new/', NewGameView.as_view(), name='game-new'),
    path('game/current/', CurrentGameView.as_view(), name='game-current'),
    path('game/guess/', SubmitGuessView.as_view(), name='game-submit-guess'),
    path('game/reveal/', RevealAnswerView.as_view(), name='game-reveal'),
    # Profile & Stats
    path('me/', MeView.as_view(), name='user-me'),
    path('me/history/', MyHistoryView.as_view(), name='user-history'),
    # Leaderboards
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    # Effects
    path('effects/trigger/', EffectTriggerView.as_view(), name='effects-trigger'),
]
