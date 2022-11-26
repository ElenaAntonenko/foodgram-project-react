import base64

from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from recipes.models import (Favorite, Follow, Ingredient, IngredientInRecipe,
                            Recipe, ShoppingCart, Tag, )
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from users.models import User


class Base64ImageField(serializers.ImageField):

    def to_internal_value(self, data):
        """Преобразование картинки"""

        if isinstance(data, str) and data.startswith('data:image'):
            format, imgstr = data.split(';base64,')
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr), name='photo.' + ext)

        return super().to_internal_value(data)


class TagSerializer(ModelSerializer):
    """Вывод тэгов."""

    class Meta:
        model = Tag
        fields = ('id', 'name', 'color', 'slug')


class IngredientSerializer(ModelSerializer):
    """вывод ингредиентов."""

    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'measurement_unit')


class UsersSerializer(serializers.ModelSerializer):
    """
    Сериализатор выдачи информации о user.
    """
    is_subscribed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_subscribed'
        )

    def get_is_subscribed(self, obj):
        """
        Проверка на подписку.
        """
        user_me = self.context['request'].user
        if not user_me.is_authenticated:
            return False
        return user_me.follower.filter(author=obj).exists()


class IngredientInRecipeSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='ingredient.id')
    name = serializers.ReadOnlyField(source='ingredient.name')
    measurement_unit = serializers.ReadOnlyField(
        source='ingredient.measurement_unit')

    class Meta:
        model = IngredientInRecipe
        fields = ('id', 'name', 'measurement_unit', 'amount')


class RecipeViewSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)
    author = UsersSerializer()
    ingredients = IngredientInRecipeSerializer(
        source='ingredient_list', many=True)
    is_favorited = serializers.SerializerMethodField()
    is_in_shopping_cart = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = (
            'id',
            'tags',
            'author',
            'ingredients',
            'is_favorited',
            'is_in_shopping_cart',
            'name',
            'image',
            'text',
            'cooking_time',
        )

    def get_is_favorited(self, obj):
        """Проверка на добавление в избранное."""

        request = self.context['request'].user
        if not request.is_authenticated:
            return False
        return Favorite.objects.filter(
            user=request, recipe=obj
        ).exists()

    def get_is_in_shopping_cart(self, obj):
        """проверка на наличие  в корзине."""

        request = self.context['request'].user
        if not request.is_authenticated:
            return False
        return ShoppingCart.objects.filter(
            user=request, recipe=obj
        ).exists()


class RecipeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для выдачи рецепта(ов) с общей информацией.
    """

    class Meta:
        model = Recipe
        fields = (
            'id',
            'name',
            'image',
            'cooking_time'
        )


class CreateIngredientsInRecipeSerializer(serializers.ModelSerializer):
    """Сериализатор для ингредиентов в рецептах"""

    id = serializers.IntegerField()
    amount = serializers.IntegerField()

    @staticmethod
    def validate_amount(value):
        """Валидация количества"""

        if value < 1:
            raise serializers.ValidationError(
                'Количество ингредиента должно быть больше 0!'
            )
        return value

    class Meta:
        model = IngredientInRecipe
        fields = ('id', 'amount')


class CreateRecipeSerializer(serializers.ModelSerializer):
    """Создание рецептов"""

    ingredients = CreateIngredientsInRecipeSerializer(many=True)
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all()
    )
    image = Base64ImageField(use_url=True)

    class Meta:
        model = Recipe
        fields = ('ingredients', 'tags', 'name',
                  'image', 'text', 'cooking_time')

    def to_representation(self, instance):
        """Представление модели"""

        serializer = RecipeViewSerializer(
            instance,
            context={
                'request': self.context.get('request')
            }
        )
        return serializer.data

    def validate(self, data):
        """Валидация ингредиентов"""

        ingredients = self.initial_data.get('ingredients')
        lst_ingredient = []

        for ingredient in ingredients:
            if ingredient['id'] in lst_ingredient:
                raise serializers.ValidationError(
                    'Ингредиенты должны быть уникальными!'
                )
            lst_ingredient.append(ingredient['id'])
        return data

    def recipe_create_or_update(self, instance, validated_data):
        """
        Метод для создания или обновления ингредиентов и тегов.
        """
        ingredients, tags = (
            validated_data.pop('ingredients'), validated_data.pop('tags')
        )
        for item in ingredients:
            cur_obj, _ = IngredientInRecipe.objects.get_or_create(
                recipe=instance,
                ingredient=get_object_or_404(Ingredient, pk=item['id']),
                amount=item['amount']
            )
        for item in tags:
            instance.tags.add(item)

        return instance

    def create(self, validated_data):
        raw_data = {
            'ingredients': validated_data.pop('ingredients'),
            'tags': validated_data.pop('tags')
        }
        recipe = Recipe.objects.create(**validated_data)
        return self.recipe_create_or_update(recipe, raw_data)

    def update(self, instance, validated_data):
        instance.ingredients.clear()
        instance.tags.clear()
        instance = self.recipe_create_or_update(instance, validated_data)
        return super().update(instance, validated_data)


class FavoriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор для выдачи избранных рецептов.
    """

    class Meta:
        model = Favorite
        fields = (
            'user',
            'recipe'
        )

    def validate(self, data):
        if Favorite.objects.filter(
                user=data['user'],
                recipe=data['recipe']
        ):
            raise serializers.ValidationError(
                f'Рецепт - {data["recipe"]} уже есть в избранном'
            )
        return data

    def to_representation(self, instance):
        return RecipeSerializer(instance.recipe).data


class FollowSerializer(UsersSerializer):
    """
    Сериализатор для выдачи подписок.
    """
    recipes_count = serializers.SerializerMethodField()
    recipes = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_subscribed',
            'recipes',
            'recipes_count'
        )

    def get_recipes(self, author):
        """
        При наличии в параметрах запроса recipes_limit происходит
        выдача среза списка с ингредиентами.
        """
        request = self.context.get('request')
        recipes_limit = request.query_params.get('recipes_limit')
        if recipes_limit:
            return RecipeSerializer(
                Recipe.objects.filter(author=author)[:int(recipes_limit)],
                context={'queryset': request},
                many=True
            ).data
        return RecipeSerializer(
            Recipe.objects.filter(author=author),
            context={'queryset': request},
            many=True
        ).data

    def get_recipes_count(self, obj):
        """
        Подсчет количества рецептов автора.
        """
        return obj.recipes.count()


class FollowPostSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создание запроса на подписку.
    """

    class Meta:
        model = Follow
        fields = (
            'author',
            'user'
        )

    def validate(self, data):
        user_me = self.context['request'].user
        if user_me == data['author']:
            raise serializers.ValidationError(
                'Нельзя подписываться на самого себя!'
            )
        if Follow.objects.filter(
                author=data['author'],
                user=user_me):
            raise serializers.ValidationError(
                f'Вы подписаны на автора {data["author"]}!'
            )
        return data

    def to_representation(self, instance):
        return FollowSerializer(
            instance.author,
            context={'request': self.context.get('request')}
        ).data


class ShoppingCartSerializer(serializers.ModelSerializer):
    """
    Сериализатор для списка покупок автора.
    """

    class Meta:
        model = ShoppingCart
        fields = (
            'user',
            'recipe'
        )

    def validate(self, data):
        if ShoppingCart.objects.filter(
                user=data['user'],
                recipe=data['recipe']
        ):
            raise serializers.ValidationError(
                f'Рецепт - {data["recipe"]} уже есть в списке покупок'
            )
        return data

    def to_representation(self, instance):
        return RecipeSerializer(instance.recipe).data
