# AutoSummarize - TODO & Future Ideas

## 🚀 **High Priority Features**

### Multiple Job Queue System
- **Description**: Allow users to upload multiple files simultaneously while other jobs are processing
- **Benefits**: Better user experience, higher throughput
- **Implementation**: Extend ThreadPoolExecutor, add job queue UI
- **Status**: Idea stage - implement when requested

### Real-time Job Status in History
- **Description**: Show processing jobs in history page so users can track progress even after navigating away
- **Benefits**: Better UX for long-running jobs, progress persistence across page refreshes
- **Implementation**: 
  - Save jobs to history immediately when started (with "PROCESSING" status)
  - Update history in real-time via polling or websockets
  - Show progress bar in history cards for active jobs
- **Status**: High priority - implement soon

### Display Job ID During Processing
- **Description**: Show the job ID on the upload page while processing
- **Benefits**: Users can reference specific jobs, easier debugging
- **Implementation**: Add job ID display in status area
- **Status**: Easy win - implement soon

## 🎯 **Medium Priority Features**

### Dynamic Model Selection from Gemini API
- **Description**: Fetch available Gemini models from API instead of hardcoding
- **Benefits**: Always up-to-date model list, automatic new model support
- **Implementation**: Add API call to fetch models, cache for performance
- **Status**: Nice to have

### Enhanced Error Handling
- **Description**: Better error messages for various failure scenarios
- **Current Issues**: 
  - File size errors could be clearer
  - Network errors need better handling
  - API failures need specific messages
- **Status**: Partially implemented

### Date/Time Formatting Optimization
- **Description**: Improve timestamp display in history
- **Current Issue**: Timestamps show when job was created, should show completion time
- **Improvement**: Show hour:minute format, save storage space
- **Status**: Minor improvement needed

## 🔧 **Technical Improvements**

### WebSocket Integration (Optional)
- **Description**: Replace polling with WebSocket for real-time updates
- **Benefits**: Lower latency, reduced server load
- **Trade-offs**: More complex, less reliable than HTTP polling
- **Status**: Not needed currently - polling works well

### Job Persistence
- **Description**: Ensure jobs survive server restarts
- **Implementation**: Enhanced database storage, job recovery on startup
- **Status**: Consider for production deployment

### Performance Optimizations
- **Description**: Optimize for large files and concurrent users
- **Ideas**: 
  - Chunked upload progress
  - Background job cleanup
  - Memory usage optimization
- **Status**: Monitor and implement as needed

## 💡 **UI/UX Enhancements**

### Advanced Progress Visualization
- **Description**: More detailed progress indicators
- **Ideas**:
  - Step-by-step progress indicator
  - Estimated time remaining
  - Processing stage visualization
- **Status**: Partially implemented with current progress bar

### Responsive Design Improvements
- **Description**: Better mobile experience
- **Areas**: File upload on mobile, history page layout
- **Status**: Basic responsive design implemented

### Dark Mode Polish
- **Description**: Ensure all components look great in dark mode
- **Status**: Mostly complete, minor tweaks as needed

## 🔐 **Security & Privacy**

### Enhanced File Validation
- **Description**: More robust server-side file validation
- **Implementation**: Magic number checking, content analysis
- **Status**: Basic validation implemented

### API Key Security
- **Description**: Better API key storage and validation
- **Ideas**: Encryption at rest, key validation UI
- **Status**: Basic security implemented

## 📊 **Analytics & Monitoring**

### Usage Analytics
- **Description**: Track usage patterns and performance metrics
- **Privacy**: Ensure user privacy while gathering insights
- **Status**: Future consideration

### Health Monitoring
- **Description**: Monitor application health and performance
- **Implementation**: Logging, metrics collection
- **Status**: Basic logging implemented

---

## 📝 **Notes**

- **Priority System**: Features are organized by impact and complexity
- **Status Tracking**: Each item has a current status to track progress
- **User Feedback**: Regular updates based on user testing and feedback
- **Incremental Implementation**: Focus on small, impactful improvements

---

## 🗂️ **Completed Items**

### ✅ Real-time Progress Tracking
- **Completed**: August 6, 2025
- **Description**: Added comprehensive progress tracking throughout processing pipeline
- **Impact**: Significantly improved user experience during file processing

### ✅ Markdown Rendering
- **Completed**: August 6, 2025  
- **Description**: Added Marked.js for proper summary/transcript formatting
- **Impact**: Much better readability of results

### ✅ Enhanced Progress Bar Animations
- **Completed**: August 6, 2025
- **Description**: Added gradient animations, pulse effects, and percentage display
- **Impact**: More engaging and informative progress visualization

### ✅ Large File Processing Bug Fix
- **Completed**: August 6, 2025
- **Description**: Fixed critical type comparison error for files longer than 30 minutes
- **Bug**: `'<=' not supported between instances of 'float' and 'str'` when comparing duration with max_duration_seconds
- **Solution**: Ensured max_duration_seconds is always converted to integer in settings loading
- **Impact**: Large files (30+ minutes) can now be processed without errors

### ✅ File Size Limit Fix
- **Completed**: August 6, 2025
- **Description**: Better file validation and error display
- **Impact**: Clearer feedback for users when errors occur

---

*This TODO list is regularly updated based on user feedback and development priorities.*
