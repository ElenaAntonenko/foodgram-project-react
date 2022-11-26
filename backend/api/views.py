from recipes.models import (IngredientInRecipe,
                            ShoppingCart)
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from .permissions import IsAuthorOrReadOnly
from .serializer import (FavoriteSerializer,
                         CreateRecipeSerializer,
                         RecipeViewSerializer, ShoppingCartSerializer
                         )

from recipes.models import Follow
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from djoser.serializers import SetPasswordSerializer, UserCreateSerializer
from recipes.models import (Favorite, Ingredient, Recipe,
                            Tag)
from rest_framework import mixins, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from .filters import IngredientFilter, RecipeFilter

from .serializer import (FollowPostSerializer,
                         FollowSerializer,
                         IngredientSerializer,
                         TagSerializer,
                         UsersSerializer)

User = get_user_model()


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """Вьюсет работы с обьектами класса Tag."""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = (AllowAny,)
    pagination_class = None


class IngredientViewSet(viewsets.ReadOnlyModelViewSet):
    """Вьюсет для работы с обьектами класса Ingredient."""
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = IngredientFilter
    search_fields = ('^name',)
    pagination_class = None


class UsersViewSet(mixins.ListModelMixin,
                   mixins.CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   GenericViewSet):
    """
    Контроллер для обработки ресурса /users/.
    """
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        if self.action == 'subscriptions':
            subscriptions = self.request.user.follower.values('author')
            return User.objects.filter(
                pk__in=[pk['author'] for pk in subscriptions]
            )
        return User.objects.order_by('id').all()

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action == 'set_password':
            return SetPasswordSerializer
        if self.action == 'subscriptions':
            return FollowSerializer
        if self.action == 'subscribe':
            return FollowPostSerializer
        return UsersSerializer

    def get_permissions(self):
        if self.action in (
                'retrieve',
                'me',
                'set_password',
                'subscribe',
                'subscriptions'
        ):
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    @action(['get'], detail=False)
    def me(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.request.user)
        return Response(serializer.data)

    @action(["post"], detail=False)
    def set_password(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.request.user.set_password(serializer.data["new_password"])
        self.request.user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=['GET'], detail=False)
    def subscriptions(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            self.paginate_queryset(self.get_queryset()),
            many=True
        )
        return self.get_paginated_response(serializer.data)

    @action(methods=['POST'], detail=True)
    def subscribe(self, request, *args, **kwargs):
        data = {
            'author': self.get_object().pk,
            'user': self.request.user.pk,
        }
        serializer = FollowPostSerializer(
            data=data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            data=serializer.data,
            status=status.HTTP_201_CREATED
        )

    @subscribe.mapping.delete
    def subscribe_delete(self, request, pk):
        follow = Follow.objects.filter(
            author=self.get_object(),
            user=self.request.user
        )
        if not follow:
            raise ValidationError(
                'Вы не были подписаны на автора'
            )
        follow.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecipeViewSet(ModelViewSet):
    """ViewSet для обработки запросов, связанных с рецептами."""
    queryset = Recipe.objects.all()
    permission_classes = (IsAuthorOrReadOnly,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter

    def get_serializer_class(self):
        """Метод для вызова определенного сериализатора. """

        if self.action in ('list', 'retrieve'):
            return RecipeViewSerializer
        elif self.action in ('create', 'partial_update'):
            return CreateRecipeSerializer

    def get_serializer_context(self):
        """Метод для передачи контекста. """

        context = super().get_serializer_context()
        context.update({'request': self.request})
        return context

    @action(
        detail=True,
        methods=('post',),
        permission_classes=(IsAuthenticated,),
        url_path='favorite',
        url_name='favorite',
    )
    def favorite(self, request, pk):
        """Метод для управления избранными подписками """
        recipe = get_object_or_404(Recipe, id=pk)
        data = {
            'user': request.user.pk,
            'recipe': recipe.pk
        }
        serializer = FavoriteSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @favorite.mapping.delete
    def delete_recipe(self, request, pk):
        """
        Вызывается методом: favorite, shopping_cart.
        Проверяет наличие рецепта в избранных или корзине
        и удаляет его.
        """

        favorite = Favorite.objects.filter(
            user=request.user.pk,
            recipe=get_object_or_404(Recipe, pk=pk)
        )
        if not favorite:
            raise ValidationError(
                'Рецепта в избранном нет!'
            )
        favorite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=('post',),
        permission_classes=(IsAuthenticated,),
        url_path='shopping_cart',
        url_name='shopping_cart',
    )
    def shopping_cart(self, request, *args, **kwargs):
        """Метод для управления списком покупок"""
        recipe = get_object_or_404(Recipe, id=self.kwargs['pk'])
        data = {
            'user': request.user.pk,
            'recipe': recipe.pk
        }
        serializer = ShoppingCartSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @shopping_cart.mapping.delete
    def shopping_cart_delete(self, request, pk):
        shopping = ShoppingCart.objects.filter(
            user=request.user.pk,
            recipe=get_object_or_404(Recipe, id=pk)
        )
        if not shopping:
            raise ValidationError(
                'Рецепта в спске покупок нет!'
            )
        shopping.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def ingredients_to_txt(ingredients):
        """Метод для объединения ингредиентов в список для загрузки"""

        shopping_list = ''
        for ingredient in ingredients:
            shopping_list += (
                f"{ingredient['ingredient__name']}  - "
                f"{ingredient['sum']}"
                f"({ingredient['ingredient__measurement_unit']})\n"
            )
        return shopping_list

    @action(
        detail=False,
        methods=('get',),
        permission_classes=(IsAuthenticated,),
        url_path='download_shopping_cart',
        url_name='download_shopping_cart',
    )
    def download_shopping_cart(self, request):
        """Метод для загрузки ингредиентов и их количества
         для выбранных рецептов"""

        ingredients = IngredientInRecipe.objects.filter(
            recipe__shopping_recipe__user=request.user
        ).values(
            'ingredient__name',
            'ingredient__measurement_unit'
        ).annotate(sum=Sum('amount'))
        shopping_list = self.ingredients_to_txt(ingredients)
        return HttpResponse(shopping_list, content_type='text/plain')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
