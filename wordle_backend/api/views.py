from __future__ import annotations

import random

from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, Guess, UserProfile, Word, ensure_user_profile
from .serializers import (
    EffectTriggerSerializer,
    GameSerializer,
    LoginSerializer,
    MessageSerializer,
    NewGameSerializer,
    RegisterSerializer,
    SubmitGuessSerializer,
    UserProfileSerializer,
    UserSerializer,
    score_guess,
)

User = get_user_model()


@api_view(["GET"])
def health(request):
    """
    Health check endpoint.

    Summary:
    Returns a simple message to confirm the server is running.

    Returns:
        200 OK with {"message": "Server is up!"}
    """
    return Response({"message": "Server is up!"})


# -----------------------
# Authentication Endpoints
# -----------------------

class RegisterView(APIView):
    """
    Register a new user with username, email and password.
    """

    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_id="auth_register",
        operation_summary="Register a new user",
        operation_description="Create a user account with username, email and password.",
        request_body=RegisterSerializer,
        responses={201: UserSerializer, 400: "Bad Request"},
        tags=["auth"],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            ensure_user_profile(user)
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    Login a user using username and password (session-based auth).
    """

    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_id="auth_login",
        operation_summary="Login",
        operation_description="Authenticate with username and password; sets session cookie.",
        request_body=LoginSerializer,
        responses={200: UserSerializer, 400: "Bad Request"},
        tags=["auth"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            login(request, user)
            return Response(UserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    Logout the current user by clearing the session cookie.
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="auth_logout",
        operation_summary="Logout",
        operation_description="Logs out the current session.",
        responses={200: MessageSerializer},
        tags=["auth"],
    )
    def post(self, request):
        logout(request)
        return Response({"message": "Logged out"})


class PasswordResetRequestView(APIView):
    """
    Generate a reset token and email it to the user.
    For demo/local dev, email backend may print to console.
    """

    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_id="auth_password_reset_request",
        operation_summary="Request password reset",
        operation_description="Send a password reset token to the user's email.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email"],
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING, description="User email"),
            },
        ),
        responses={200: MessageSerializer},
        tags=["auth"],
    )
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"email": "This field is required."}, status=400)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal whether user exists.
            return Response({"message": "If an account exists, you will receive an email shortly."})
        token = default_token_generator.make_token(user)
        # In production, configure EMAIL_* settings and provide a real reset URL.
        reset_link = f"/reset-password?uid={user.pk}&token={token}"
        try:
            send_mail(
                subject="Wordle Password Reset",
                message=f"Use the following link to reset your password: {reset_link}",
                from_email=None,
                recipient_list=[email],
                fail_silently=True,
            )
        except Exception:
            # If email backend not configured, still respond OK for UX.
            pass
        return Response({"message": "If an account exists, you will receive an email shortly."})


class PasswordResetConfirmView(APIView):
    """
    Reset password using uid and token from the email.
    """

    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_id="auth_password_reset_confirm",
        operation_summary="Confirm password reset",
        operation_description="Submit new password along with uid and token.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["uid", "token", "new_password"],
            properties={
                "uid": openapi.Schema(type=openapi.TYPE_INTEGER, description="User ID"),
                "token": openapi.Schema(type=openapi.TYPE_STRING, description="Reset token"),
                "new_password": openapi.Schema(type=openapi.TYPE_STRING, description="New password"),
            },
        ),
        responses={200: MessageSerializer, 400: "Bad Request"},
        tags=["auth"],
    )
    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        new_password = request.data.get("new_password")
        if not all([uid, token, new_password]):
            return Response({"message": "uid, token and new_password are required."}, status=400)
        try:
            user = User.objects.get(pk=uid)
        except User.DoesNotExist:
            return Response({"message": "Invalid user."}, status=400)
        if not default_token_generator.check_token(user, token):
            return Response({"message": "Invalid token."}, status=400)
        user.set_password(new_password)
        user.save()
        return Response({"message": "Password has been reset."})


# -----------------------
# Gameplay Endpoints
# -----------------------

def _get_random_active_word(length: int = 5) -> Word:
    qs = Word.objects.filter(is_active=True, length=length)
    count = qs.count()
    if count == 0:
        # seed minimal set if none exists
        seed = ["adieu", "crane", "slate", "ghost", "party", "light", "disco"]
        random.shuffle(seed)
        for w in seed:
            Word.objects.get_or_create(text=w, defaults={"is_active": True, "length": len(w)})
        qs = Word.objects.filter(is_active=True, length=length)
        count = qs.count()
    idx = random.randint(0, count - 1)
    return qs[idx]


class NewGameView(APIView):
    """
    Start a new Wordle game for the authenticated user.
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="game_new",
        operation_summary="Start a new game",
        operation_description="Creates a new game with a random target word and returns the game.",
        request_body=NewGameSerializer,
        responses={201: GameSerializer},
        tags=["gameplay"],
    )
    def post(self, request):
        serializer = NewGameSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        max_attempts = serializer.validated_data.get("max_attempts", 6)
        word = _get_random_active_word(length=5)
        game = Game.objects.create(user=request.user, target_word=word, max_attempts=max_attempts)
        return Response(GameSerializer(game).data, status=status.HTTP_201_CREATED)


class CurrentGameView(APIView):
    """
    Get the user's current active game (if any).
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="game_current",
        operation_summary="Get current active game",
        responses={200: GameSerializer, 204: "No Content"},
        tags=["gameplay"],
    )
    def get(self, request):
        game = Game.objects.filter(user=request.user, ended_at__isnull=True).order_by("-created_at").first()
        if not game:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(GameSerializer(game).data)


class SubmitGuessView(APIView):
    """
    Submit a guess for a game and receive scoring results.
    Triggers effects: 'disco' and 'party_popper' for wins, 'ghost' for losses or incorrect.
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="game_submit_guess",
        operation_summary="Submit guess",
        operation_description="Submit a guess for the current active game or a specific game_id.",
        request_body=SubmitGuessSerializer,
        manual_parameters=[
            openapi.Parameter(
                "game_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False, description="Optional game id"
            )
        ],
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
        tags=["gameplay", "effects"],
    )
    @transaction.atomic
    def post(self, request):
        game_id = request.query_params.get("game_id")
        if game_id:
            game = get_object_or_404(Game, pk=game_id, user=request.user)
        else:
            game = Game.objects.filter(user=request.user, ended_at__isnull=True).order_by("-created_at").first()
            if not game:
                return Response({"message": "No active game."}, status=400)

        if not game.is_active:
            return Response({"message": "Game already ended."}, status=400)

        serializer = SubmitGuessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guess_text = serializer.validated_data["guess"]

        if len(guess_text) != game.target_word.length:
            return Response({"message": f"Guess must be {game.target_word.length} letters."}, status=400)

        # Optional: validate word exists in dictionary
        if not Word.objects.filter(text=guess_text).exists():
            # Allow unknown words but mark as absent letters; alternatively reject:
            # return Response({"message": "Not in word list."}, status=400)
            pass

        result = score_guess(guess_text, game.target_word.text)
        Guess.objects.create(game=game, text=guess_text, result=result)

        guesses_count = game.guesses.count()
        response_payload = {
            "guess": guess_text,
            "result": result,
            "attempt_number": guesses_count,
            "max_attempts": game.max_attempts,
            "effects": [],  # hints for frontend
            "status": "in_progress",
        }

        if all(r == "correct" for r in result):
            # Win
            game.end_game(won=True, attempts_used=guesses_count)
            ensure_user_profile(request.user).record_game(
                won=True, attempts_used=guesses_count, duration_seconds=game.duration_seconds
            )
            response_payload["status"] = "won"
            response_payload["effects"] = ["disco", "party_popper"]
        elif guesses_count >= game.max_attempts:
            # Loss
            game.end_game(won=False, attempts_used=guesses_count)
            ensure_user_profile(request.user).record_game(
                won=False, attempts_used=guesses_count, duration_seconds=game.duration_seconds
            )
            response_payload["status"] = "lost"
            response_payload["target"] = game.target_word.text
            response_payload["effects"] = ["ghost"]
        else:
            # Still going; incorrect guess triggers subtle effect
            response_payload["effects"] = ["shake"]

        return Response(response_payload, status=200)


class RevealAnswerView(APIView):
    """
    Reveal the answer for a finished game (or active if desired).
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="game_reveal",
        operation_summary="Reveal target word",
        operation_description="Returns the target word for the specified game if it belongs to the user.",
        manual_parameters=[
            openapi.Parameter(
                "game_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True, description="Game id"
            )
        ],
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
        tags=["gameplay"],
    )
    def get(self, request):
        game_id = request.query_params.get("game_id")
        game = get_object_or_404(Game, pk=game_id, user=request.user)
        return Response({"target": game.target_word.text})


# -----------------------
# Profile & Stats
# -----------------------

class MeView(APIView):
    """
    Get current user and profile/stats.
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="user_me",
        operation_summary="Current user profile",
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
        tags=["profile"],
    )
    def get(self, request):
        profile = ensure_user_profile(request.user)
        return Response({"user": UserSerializer(request.user).data, "profile": UserProfileSerializer(profile).data})


class MyHistoryView(APIView):
    """
    Get user's recent games, with pagination-like limit parameter.
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="user_history",
        operation_summary="User game history",
        manual_parameters=[
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Number of recent games (default 20)",
            )
        ],
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
        tags=["profile"],
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 20))
        games = Game.objects.filter(user=request.user).order_by("-created_at")[: max(1, min(limit, 100))]
        return Response({"games": GameSerializer(games, many=True).data})


# -----------------------
# Leaderboards
# -----------------------

class LeaderboardView(APIView):
    """
    Generic leaderboard endpoint supporting different metrics.
    Supported types: 'streak', 'win_rate', 'fastest', 'best_attempts'.
    """

    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_id="leaderboard_list",
        operation_summary="Leaderboards",
        operation_description="Return top users by type: streak, win_rate, fastest, best_attempts.",
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=["streak", "win_rate", "fastest", "best_attempts"],
                required=True,
                description="Leaderboard type",
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Number of entries (default 20, max 100)",
            ),
        ],
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
        tags=["leaderboard"],
    )
    def get(self, request):
        lb_type = request.query_params.get("type")
        limit = int(request.query_params.get("limit", 20))
        limit = max(1, min(limit, 100))

        qs = UserProfile.objects.select_related("user")

        if lb_type == "streak":
            qs = qs.order_by("-current_streak", "-max_streak", "user__username")
            data = [
                {
                    "username": p.user.username,
                    "current_streak": p.current_streak,
                    "max_streak": p.max_streak,
                }
                for p in qs[:limit]
            ]
        elif lb_type == "win_rate":
            # order by computed win_rate; approximate using ratio fields
            # avoid division-by-zero by ordering with cases, but here we pull and sort in python for simplicity
            profiles = list(qs)
            profiles.sort(key=lambda p: (0 if p.games_played == 0 else p.games_won / p.games_played), reverse=True)
            data = [
                {
                    "username": p.user.username,
                    "games_played": p.games_played,
                    "games_won": p.games_won,
                    "win_rate": p.win_rate,
                }
                for p in profiles[:limit]
            ]
        elif lb_type == "fastest":
            qs = qs.exclude(fastest_solve_seconds__isnull=True).order_by("fastest_solve_seconds", "user__username")
            data = [
                {
                    "username": p.user.username,
                    "fastest_solve_seconds": p.fastest_solve_seconds,
                }
                for p in qs[:limit]
            ]
        elif lb_type == "best_attempts":
            qs = qs.exclude(best_attempt_count__isnull=True).order_by("best_attempt_count", "user__username")
            data = [
                {
                    "username": p.user.username,
                    "best_attempt_count": p.best_attempt_count,
                }
                for p in qs[:limit]
            ]
        else:
            return Response({"message": "Invalid leaderboard type."}, status=400)

        return Response({"type": lb_type, "results": data})


# -----------------------
# Effects
# -----------------------

class EffectTriggerView(APIView):
    """
    Allows frontend to request a specific effect to be triggered,
    e.g., 'party_popper', 'disco', 'ghost', or 'shake'.
    No server-side state is changed; this is advisory metadata for UI.
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="effects_trigger",
        operation_summary="Trigger UI effect",
        operation_description="Returns effect payload for the frontend to render celebratory or ghost effects.",
        request_body=EffectTriggerSerializer,
        responses={200: openapi.Schema(type=openapi.TYPE_OBJECT)},
        tags=["effects"],
    )
    def post(self, request):
        serializer = EffectTriggerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"effect": serializer.validated_data["effect"], "context": serializer.validated_data.get("context", {})})


# -----------------------
# OpenAPI Tags metadata helper (optional; used by drf-yasg UI)
# -----------------------

openapi_tags = [
    {"name": "auth", "description": "User authentication endpoints"},
    {"name": "gameplay", "description": "Core Wordle gameplay"},
    {"name": "profile", "description": "User profile and statistics"},
    {"name": "leaderboard", "description": "Leaderboards"},
    {"name": "effects", "description": "UI celebratory and ghost effects"},
]
