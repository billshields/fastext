# Feature Plan: RSVP + Type Recall Mode

## Concept
A new reader mode where users speed-read a chunk of text via RSVP, then type what they remember from memory. Combines speed reading training with active recall and typing practice — inspired by entertrained.com's approach of learning through typed engagement with content.

## User Flow
1. User opens a document in the reader and enables "Type Recall" mode (toggle in settings or controls bar)
2. RSVP plays a **segment** (e.g., one sentence or N words) at the user's set WPM
3. After the segment finishes, the RSVP display transitions to a **typing input area**
4. User types what they remember from the segment
5. On submit (Enter or button), the app scores their recall:
   - Words matched (order-sensitive)
   - Accuracy percentage
   - Typing speed (WPM while typing)
6. A brief **results overlay** shows: the original text, the user's text, highlighted matches/misses
7. User presses Space or clicks to advance to the next segment
8. Progress is tracked and stats accumulate per session

## Segment Strategy
- **Default**: One sentence (use `sentence_end` flags already in DocumentChunk)
- **Configurable**: Fixed word count (5, 10, 15, 20 words) or sentence-based
- Segment boundaries should align with sentence ends when possible
- Longer segments = harder recall challenge

## Architecture

### Backend Changes

#### New Model: `RecallAttempt` (`apps/reading/models.py`)
```python
class RecallAttempt(models.Model):
    session = models.ForeignKey(ReadingSession, on_delete=models.CASCADE, related_name='recall_attempts')
    segment_start = models.PositiveIntegerField()  # word position
    segment_end = models.PositiveIntegerField()
    original_text = models.TextField()
    typed_text = models.TextField()
    accuracy = models.FloatField()  # 0.0 - 1.0
    words_matched = models.PositiveIntegerField()
    words_total = models.PositiveIntegerField()
    typing_wpm = models.PositiveIntegerField()  # typing speed during recall
    reading_wpm = models.PositiveIntegerField()  # RSVP speed for this segment
    created_at = models.DateTimeField(auto_now_add=True)
```

#### New Serializer: `RecallAttemptSerializer` (`apps/reading/serializers.py`)
- For POST: accepts `segment_start`, `segment_end`, `typed_text`, `typing_wpm`, `reading_wpm`
- Server computes accuracy and words_matched by comparing typed_text to actual words
- For GET: returns full attempt data for stats display

#### New View: `RecallAttemptView` (`apps/reading/views.py`)
- POST `/api/documents/<doc_id>/recall/` — submit a recall attempt
  - Fetches original words from DocumentChunk for the segment range
  - Computes accuracy (word-level diff, case-insensitive, punctuation-flexible)
  - Creates RecallAttempt record
  - Returns scored result with original text highlighted
- GET `/api/documents/<doc_id>/recall/stats/` — aggregate recall stats for this document
  - Average accuracy, total attempts, accuracy trend over time

#### UserPreferences Addition
- `recall_segment_size` (PositiveSmallIntegerField, default=0) — 0 = sentence-based, >0 = fixed word count
- `recall_enabled` (BooleanField, default=False)

### Frontend Changes

#### Reader Engine (`static/js/reader.js`)
- Add `playSegment(startPos, wordCount)` method:
  - Plays from `startPos` for exactly `wordCount` words, then auto-pauses
  - Calls new `onSegmentComplete(startPos, endPos, words[])` callback
- Add `getNextSegmentBounds(fromPos)` method:
  - If sentence-based: scan forward from `fromPos` until `sentence_end === true`
  - If fixed count: return `(fromPos, fromPos + segmentSize)`
  - Returns `{ start, end, wordCount }`

#### App Controller (`static/js/app.js`)
- Add recall mode state: `recallEnabled`, `currentSegment`, `recallPhase` ('reading' | 'typing' | 'results')
- Add `onSegmentComplete` callback:
  - Transition RSVP display to typing input
  - Start typing timer
- Add `submitRecall()`:
  - POST typed text to `/api/documents/{docId}/recall/`
  - Display results overlay with diff highlighting
- Add `advanceToNextSegment()`:
  - Calculate next segment bounds
  - Play next segment via `engine.playSegment()`

#### Reader Template (`templates/reader.html`)
- Add recall typing area (hidden by default, shown during typing phase):
  ```html
  <div id="recall-area" class="recall-area" hidden>
      <p class="recall-prompt">Type what you remember:</p>
      <textarea id="recall-input" class="recall-input" rows="3" autofocus></textarea>
      <div class="recall-actions">
          <span id="recall-timer">0.0s</span>
          <button id="btn-recall-submit" class="btn btn-primary">Submit (Enter)</button>
      </div>
  </div>
  ```
- Add results overlay:
  ```html
  <div id="recall-results" class="recall-results" hidden>
      <div class="recall-score">
          <span id="recall-accuracy">0%</span> accuracy
          <span id="recall-typing-wpm">0 WPM</span> typing speed
      </div>
      <div id="recall-diff" class="recall-diff"></div>
      <button id="btn-recall-next" class="btn btn-primary">Next Segment (Space)</button>
  </div>
  ```
- Add settings toggle:
  ```html
  <div class="setting-row">
      <label>Type Recall Mode</label>
      <input type="checkbox" id="set-recall-enabled">
  </div>
  <div class="setting-row">
      <label>Segment Size</label>
      <select id="set-recall-segment">
          <option value="0">By sentence</option>
          <option value="5">5 words</option>
          <option value="10">10 words</option>
          <option value="15">15 words</option>
          <option value="20">20 words</option>
      </select>
  </div>
  ```

#### CSS (`static/css/reader.css`)
- `.recall-area`: Centered below RSVP display, same width constraints
- `.recall-input`: Dark theme textarea matching existing inputs
- `.recall-results`: Overlay or inline panel with score display
- `.recall-diff`: Word-level diff display — green for matches, red for misses, gray for missing words
- `.recall-score`: Large accuracy percentage, smaller typing WPM

### Scoring Algorithm (server-side)
```python
def score_recall(original_words, typed_words):
    """
    Word-level comparison, case-insensitive, strips punctuation for matching.
    Uses longest common subsequence for order-sensitive matching.
    """
    def normalize(w):
        return re.sub(r'[^\w]', '', w.lower())
    
    orig = [normalize(w) for w in original_words]
    typed = [normalize(w) for w in typed_words]
    
    # LCS for order-sensitive matching
    lcs_length = longest_common_subsequence(orig, typed)
    
    accuracy = lcs_length / len(orig) if orig else 0
    return {
        'words_matched': lcs_length,
        'words_total': len(orig),
        'accuracy': round(accuracy, 3),
    }
```

## UI State Machine
```
[READING] --segment complete--> [TYPING] --submit--> [RESULTS] --next--> [READING]
    |                                                      |
    +-- pause/exit recall mode --<--------------------------+
```

- **READING**: RSVP display active, playing segment. Controls dimmed except pause.
- **TYPING**: RSVP display hidden, textarea shown. Timer running. Enter submits.
- **RESULTS**: Diff display shown. Space or button advances. Stats updated.

## Files to Modify
| File | Changes |
|------|---------|
| `apps/reading/models.py` | Add `RecallAttempt` model |
| `apps/reading/serializers.py` | Add `RecallAttemptSerializer` |
| `apps/reading/views.py` | Add `RecallAttemptView`, scoring logic |
| `apps/reading/urls.py` | Add recall endpoint |
| `apps/users/models.py` | Add `recall_enabled`, `recall_segment_size` to UserPreferences |
| `apps/users/serializers.py` | Add new fields to serializer |
| `templates/reader.html` | Add recall area, results overlay, settings toggles |
| `static/js/reader.js` | Add `playSegment()`, `getNextSegmentBounds()` |
| `static/js/app.js` | Add recall mode state machine, typing handlers, results display |
| `static/css/reader.css` | Recall area, results, diff highlighting styles |

## Migration Required
- `apps/reading/migrations/` — new RecallAttempt table
- `apps/users/migrations/` — add recall fields to UserPreferences

## Future Extensions
- **Difficulty progression**: Auto-increase segment length as accuracy improves
- **Accuracy-gated advancement**: Must hit X% accuracy before moving on
- **Recall stats dashboard**: Accuracy over time, most-missed words, improvement graphs
- **Mode 1 (Type-Along)**: Real-time word-by-word typing during RSVP — can reuse much of this infrastructure
- **Mode 2 (Timed Typing)**: Show passage, type it — simpler variant, subset of this architecture
- **Leaderboards**: Compare recall accuracy across users on same documents
