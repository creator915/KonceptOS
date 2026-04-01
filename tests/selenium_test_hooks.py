# selenium_test_hooks.py
"""
Test hooks for Dou Di Zhu (Fight the Landlord) card game.
"""

# Inputs that can be triggered during testing
TEST_INPUTS = [
    ("bid_1_button", "[data-testid='bid-1']", "click"),
    ("bid_2_button", "[data-testid='bid-2']", "click"),
    ("bid_3_button", "[data-testid='bid-3']", "click"),
    ("no_bid_button", "[data-testid='no-bid']", "click"),
    ("play_button", "[data-testid='play-btn']", "click"),
    ("pass_button", "[data-testid='pass-btn']", "click"),
    ("hint_button", "[data-testid='hint-btn']", "click"),
    ("restart_button", "[data-testid='restart-btn']", "click"),
    ("canvas_click", "#gameCanvas", "click"),
]

# Outputs that can be checked after actions
TEST_OUTPUTS = [
    ("canvas_rendered", "#gameCanvas", "canvas_has_content"),
    ("ai1_card_count", "[data-testid='ai1-count']", "text_contains"),
    ("ai2_card_count", "[data-testid='ai2-count']", "text_contains"),
    ("status_bar", "#status-bar", "text_contains"),
    ("play_button_exists", "[data-testid='play-btn']", "exists"),
    ("pass_button_exists", "[data-testid='pass-btn']", "exists"),
    ("hint_button_exists", "[data-testid='hint-btn']", "exists"),
    ("bid_bar_exists", "[data-testid='bid-1']", "exists"),
    ("result_dialog", "[data-testid='result-dialog']", "exists"),
    ("bonus_cards_area", "[data-testid='bonus-cards']", "exists"),
    ("restart_button_exists", "[data-testid='restart-btn']", "exists"),
]

# JavaScript to verify canvas has been drawn on
CANVAS_CHECK_JS = """
(function() {
    var canvas = document.getElementById('gameCanvas');
    if (!canvas) return JSON.stringify({error: 'Canvas not found'});
    var ctx = canvas.getContext('2d');
    var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    var data = imageData.data;
    var nonEmpty = 0;
    for (var i = 0; i < data.length; i += 4) {
        if (data[i] !== 0 || data[i+1] !== 0 || data[i+2] !== 0 || data[i+3] !== 0) {
            nonEmpty++;
        }
    }
    var state = window.GameState;
    var result = {
        canvasHasContent: nonEmpty > 1000,
        pixelsFilled: nonEmpty,
        gamePhase: state.active_turn.phase,
        playerHandCount: state.player_hand.length,
        ai1HandCount: state.ai_hands.ai1.length,
        ai2HandCount: state.ai_hands.ai2.length,
        landlord: state.landlord_role.player,
        selectedCards: state.selected_cards.length,
        currentPlay: state.current_play ? state.current_play.pattern : null,
        gameResult: state.game_result,
        activeTurnPlayer: state.active_turn.player,
        totalDeckCards: state.deck_cards.length,
        patternClassify: (function() {
            // Test pattern classification
            var cp = window.classifyPattern;
            if (!cp) return 'classifyPattern not found';
            var single = cp([{suit:'♠', rank:'3'}]);
            var pair = cp([{suit:'♠', rank:'3'}, {suit:'♥', rank:'3'}]);
            var rocket = cp([{suit:'🃏', rank:'SmallJoker'}, {suit:'★', rank:'BigJoker'}]);
            return {
                single: single ? single.pattern : null,
                pair: pair ? pair.pattern : null,
                rocket: rocket ? rocket.pattern : null
            };
        })()
    };
    return JSON.stringify(result);
})();
"""

EXPECTED_BEHAVIOR = """
1. GAME INITIALIZATION:
   - On page load, 54 cards are shuffled and dealt: 17 to each player, 3 reserved as bonus cards.
   - The canvas renders a green felt table with card backs for AI players and face-up cards for the human player.
   - The bidding phase begins with bid buttons visible.

2. BIDDING PHASE:
   - Human player sees Bid 1, Bid 2, Bid 3, and No Bid buttons.
   - Clicking a bid button submits the bid. AI players bid automatically after delays.
   - Higher bids (up to 3) are valid. Bidding 3 immediately wins landlord.
   - If no one bids, a random player is assigned landlord.
   - After bidding resolves, the 3 bonus cards are given to the landlord.
   - The game transitions to the playing phase.

3. PLAYING PHASE:
   - The landlord plays first. Turn order is counter-clockwise (human -> ai1 -> ai2).
   - Human clicks cards on canvas to select/deselect them (cards pop up when selected).
   - Play button is enabled only when selected cards form a valid pattern that beats the current play.
   - Pass button is enabled when it's not the human's free turn (someone else started the round).
   - Hint button suggests a valid play by selecting appropriate cards.
   - AI players automatically choose and play cards or pass after a 1-second delay.
   - Valid patterns: single, pair, triple, triple+1, triple+2, straight (5+), consecutive pairs (3+), airplane, bomb (4 same), rocket (both jokers).
   - Bombs beat any non-bomb; rockets beat everything.
   - After 2 consecutive passes, the last player who played starts a new round (free play).

4. WIN DETECTION:
   - When any player plays their last card(s), the game checks if landlord or farmers won.
   - A result dialog appears showing win/loss, with a "Play Again" button.

5. RESTART:
   - Clicking "Play Again" resets all state and starts a new game from dealing/bidding.

6. UI ELEMENTS:
   - AI card counts displayed as numbers (not revealing card faces).
   - Landlord indicated with a crown emoji.
   - Current turn indicated with a green diamond marker.
   - Status bar shows current phase, landlord identity, and multiplier.
   - Bonus cards displayed in top-right corner after bidding.
"""